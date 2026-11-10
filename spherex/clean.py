"""Lesson 5 - subtract ZODI, mask bad pixels with FLAGS."""
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

# Pixels with any of these problems are not real sky -> NaN.
# NOT here: MP_SOURCE (marks known stars - masking it deletes your target), MP_PERSIST (optional).
BAD_FLAGS = ["MP_TRANSIENT", "MP_OVERFLOW", "MP_SUR_ERROR", "MP_NONFUNC", "MP_DICHROIC",
             "MP_MISSING_DATA", "MP_HOT", "MP_COLD", "MP_NONLINEAR"]


def flag_bits(flags_header):
    """FLAGS header -> {'MP_TRANSIENT': 0, 'MP_OVERFLOW': 1, ...} read from the file itself."""
    return {k: int(v) for k, v in flags_header.items() if k.startswith("MP_")}


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


def clean_frame(path, bad_flags=BAD_FLAGS):
    """SPHEREx MEF path -> dict:
    image (IMAGE - ZODI, bad = NaN), variance (bad = NaN), bad (bool mask), flags, bits,
    zodi, raw, wcs, header, mjd."""
    with fits.open(path) as h:
        img = h["IMAGE"].data.astype(float)
        zodi = h["ZODI"].data.astype(float)
        var = h["VARIANCE"].data.astype(float)
        flags = h["FLAGS"].data.astype(np.int64)
        bits = flag_bits(h["FLAGS"].header)
        hdr = h["IMAGE"].header
    bad = (flags & make_mask_value(bits, bad_flags)) != 0
    bad |= ~np.isfinite(img)
    return {"image": np.where(bad, np.nan, img - zodi), "variance": np.where(bad, np.nan, var),
            "bad": bad, "flags": flags, "bits": bits, "zodi": zodi, "raw": img,
            "wcs": WCS(hdr), "header": hdr, "mjd": hdr.get("MJD-AVG")}
