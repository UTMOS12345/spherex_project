"""Lesson 5 - subtract ZODI, mask bad pixels with FLAGS."""
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import binary_dilation

# Pixels with any of these problems are not real sky -> NaN.
# NOT here: MP_SOURCE (marks known stars - masking it deletes your target), MP_PERSIST (optional).
# MP_OVERFLOW on its own is NOT bad: those pixels still have a valid, corrected value
# (SPHEREx Explanatory Supplement; IRSA's own photometry keeps them). OVERFLOW together with
# SUR_ERROR ("early overflow") has no value at all - SUR_ERROR in this list catches that.
BAD_FLAGS = ["MP_TRANSIENT", "MP_SUR_ERROR", "MP_NONFUNC", "MP_DICHROIC", "MP_MISSING_DATA",
             "MP_HOT", "MP_COLD", "MP_NONLINEAR", "MP_PERSIST", "MP_BLOOM"]

# Bit numbers from the SPHEREx Explanatory Supplement (Table 16). Used when a file's FLAGS
# header does not list them as MP_<NAME> keywords (newer QR3 files use a different format).
DEFAULT_BITS = {"MP_TRANSIENT": 0, "MP_OVERFLOW": 1, "MP_SUR_ERROR": 2, "MP_PHANTOM": 4,
                "MP_REFERENCE": 5, "MP_NONFUNC": 6, "MP_DICHROIC": 7, "MP_MISSING_DATA": 9,
                "MP_HOT": 10, "MP_COLD": 11, "MP_FULLSAMPLE": 12, "MP_PHANMISS": 14,
                "MP_NONLINEAR": 15, "MP_PERSIST": 17, "MP_OUTLIER": 19, "MP_CROSSTALK": 20,
                "MP_SOURCE": 21, "MP_GHOST": 22, "MP_GHOST_FPA": 23, "MP_GHOST_EXT": 24,
                "MP_STREAK": 25, "MP_BLOOM": 26, "MP_SNOWBALL": 27, "MP_HALO": 28,
                "MP_SATELLITE_HALO": 29}


def flag_bits(flags_header):
    """FLAGS header -> {'MP_TRANSIENT': 0, 'MP_OVERFLOW': 1, ...}, read from the file itself.
    Older files list them as MP_<NAME> = bit. Newer ones (pipeline v27+) use
    MSKNnnnn = '<NAME>' (bit nnnn). If the header has neither, the standard bit numbers
    from the Explanatory Supplement are used - otherwise NO flag would be recognised and
    every bad pixel would pass as good."""
    bits = {k: int(v) for k, v in flags_header.items() if k.startswith("MP_")}
    if not bits:
        bits = {f"MP_{str(v).strip()}": int(k[4:]) for k, v in flags_header.items()
                if k.startswith("MSKN") and k[4:].isdigit()}
    return bits if bits else dict(DEFAULT_BITS)


def make_mask_value(bits, names):
    """Flag names -> one integer with those bits set (e.g. bits 0,1,2 -> 7)."""
    value = 0
    for n in names:
        if n in bits:
            value |= 1 << bits[n]
    return value


def decode_flags(value, bits):
    """One pixel's flag integer -> list of flag names that are set."""
    return [name for name, b in bits.items() if int(value) & (1 << b)]


# Flags a very bright star triggers by itself (its core saturates).
SATURATION_FLAGS = ["MP_OVERFLOW", "MP_SUR_ERROR", "MP_NONLINEAR", "MP_BLOOM"]


def _grow(mask, r):
    """True/False image -> same, with every True area grown by r pixels in all directions
    (a (2r+1) x (2r+1) square). Growth stops at the image border: nothing wraps around
    to the opposite edge (np.roll would do that)."""
    if r <= 0:
        return mask.copy()
    return binary_dilation(mask, structure=np.ones((2 * r + 1, 2 * r + 1), bool))


def saturated_mask(flags, bits, img):
    """True where a pixel is part of a SATURATED star core: early overflow
    (OVERFLOW + SUR_ERROR), a BLOOM pixel, or a pixel with no value (NaN)."""
    early = np.zeros(flags.shape, bool)
    if "MP_OVERFLOW" in bits and "MP_SUR_ERROR" in bits:
        early = ((flags & (1 << bits["MP_OVERFLOW"])) != 0) & ((flags & (1 << bits["MP_SUR_ERROR"])) != 0)
    bloom = (flags & (1 << bits["MP_BLOOM"])) != 0 if "MP_BLOOM" in bits else np.zeros(flags.shape, bool)
    return early | bloom | ~np.isfinite(img)


def clean_frame(path, bad_flags=BAD_FLAGS, keep_saturated_stars=False, bloom_radius=4):
    """SPHEREx MEF path -> dict:
    image (IMAGE - ZODI, bad = NaN), variance (bad = NaN), bad (bool mask), flags, bits,
    zodi, raw, wcs, header, mjd.
    keep_saturated_stars=True: around a saturated known star, pixels flagged only for
    saturation/bloom are kept, so bright stars don't become big holes. The very core has
    no value in the file at all (NaN) and stays NaN. For pictures and stacks only: these
    values are not accurate enough for photometry."""
    with fits.open(path) as h:
        img = h["IMAGE"].data.astype(float)
        zodi = h["ZODI"].data.astype(float)
        var = h["VARIANCE"].data.astype(float)
        flags = h["FLAGS"].data.astype(np.int64)
        bits = flag_bits(h["FLAGS"].header)
        hdr = h["IMAGE"].header
    bad = (flags & make_mask_value(bits, bad_flags)) != 0
    if keep_saturated_stars and "MP_SOURCE" in bits and "MP_OVERFLOW" in bits:
        # A saturating star = a core of OVERFLOW pixels + a ring of TRANSIENT pixels (charge "bloom").
        # Forgive those flags on known-star pixels close to a saturated pixel.
        forgiven = SATURATION_FLAGS + ["MP_TRANSIENT"]
        other_problem = (flags & make_mask_value(bits, [n for n in bad_flags if n not in forgiven])) != 0
        is_star = (flags & (1 << bits["MP_SOURCE"])) != 0
        near_sat = _grow((flags & (1 << bits["MP_OVERFLOW"])) != 0, bloom_radius)
        bad &= ~(is_star & near_sat & ~other_problem)
    bad |= ~np.isfinite(img)
    return {"image": np.where(bad, np.nan, img - zodi), "variance": np.where(bad, np.nan, var),
            "bad": bad, "flags": flags, "bits": bits, "zodi": zodi, "raw": img,
            "wcs": WCS(hdr), "header": hdr, "mjd": hdr.get("MJD-AVG")}
