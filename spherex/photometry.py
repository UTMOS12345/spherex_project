"""Lesson 9 - aperture photometry in a matched band -> light curve."""
import numpy as np
import astropy.units as u
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.table import Table
from astropy.time import Time
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_area
from photutils.aperture import CircularAperture, CircularAnnulus, aperture_photometry

from .clean import clean_frame, saturated_mask, BAD_FLAGS
from .download import get_cutout
from .targets import at_time


def wavelength_at(path, x, y):
    """Wavelength (micron) and bandwidth (micron) that pixel (x, y) of this frame sees.
    SPHEREx has no filter wheel: the colour changes across the detector, and the file's
    second WCS (key 'W') is the map from pixel to wavelength."""
    with fits.open(path) as h:
        w = WCS(h["IMAGE"].header, fobj=h, key="W")
        w.sip = None                                   # distortion terms don't apply to wavelength
        wl, bw = w.pixel_to_world(x, y)
        return float(wl.to(u.um).value), float(u.Quantity(bw).to(u.um).value)


def wavelength_map(path):
    """Wavelength (micron) seen by EVERY pixel of this frame -> 2D array, same shape as IMAGE.
    Same spectral WCS (key 'W') as wavelength_at, evaluated on the whole pixel grid."""
    with fits.open(path) as h:
        ny, nx = h["IMAGE"].data.shape
        w = WCS(h["IMAGE"].header, fobj=h, key="W")
        w.sip = None
        yy, xx = np.mgrid[:ny, :nx]
        wl, _ = w.pixel_to_world(xx, yy)
        return np.asarray(wl.to(u.um).value, float).reshape(ny, nx)


def measure_frame(path, pos, r_px=2.0, sky_in=4.0, sky_out=7.0):
    """Brightness of the source at SkyCoord `pos` in one cutout file -> dict.
    Sum the pixels inside a circle of radius r_px, subtract the local sky measured in a
    ring around it, convert to milli-Jansky. ok=False when the measurement can't be trusted."""
    f = clean_frame(path)                              # strict mask: no saturated pixels, no filling
    img, var = f["image"], f["variance"]
    x, y = (float(v) for v in f["wcs"].world_to_pixel(pos))
    ny, nx = img.shape
    out = {"mjd": f["mjd"], "detector": int(f["header"]["DETECTOR"]), "x": x, "y": y,
           "wavelength_um": np.nan, "flux_mjy": np.nan, "err_mjy": np.nan, "flux_min_mjy": np.nan,
           "n_bad": 0, "saturated": False, "bad_flags": "", "ok": False}
    if not (sky_out <= x < nx - sky_out and sky_out <= y < ny - sky_out):
        return out                                     # too close to the edge
    out["wavelength_um"], _ = wavelength_at(path, x, y)

    circle = CircularAperture((x, y), r=r_px)
    ring = CircularAnnulus((x, y), r_in=sky_in, r_out=sky_out)
    in_circle = circle.to_mask(method="center").to_image(img.shape).astype(bool)
    out["n_bad"] = int(f["bad"][in_circle].sum())      # masked pixels inside the circle
    near = (np.hypot(*np.mgrid[:ny, :nx] - np.array([y, x])[:, None, None]) <= 2.5)   # within 2.5 px
    out["saturated"] = bool(saturated_mask(f["flags"], f["bits"], f["raw"])[near].any())
    found = [n for n in BAD_FLAGS if n in f["bits"] and
             ((f["flags"][in_circle] & (1 << f["bits"][n])) != 0).any()]
    out["bad_flags"] = ",".join(n.removeprefix("MP_") for n in found)   # which problems are in the circle

    ring_pixels = img[ring.to_mask(method="center").to_image(img.shape).astype(bool)]
    _, sky, _ = sigma_clipped_stats(ring_pixels[np.isfinite(ring_pixels)])   # median, ignoring stars
    phot = aperture_photometry(np.nan_to_num(img - sky), circle,
                               error=np.sqrt(np.nan_to_num(var)))
    to_mjy = proj_plane_pixel_area(f["wcs"]) * (np.pi / 180) ** 2 * 1e9      # MJy/sr * pixel area -> mJy
    out["flux_mjy"] = float(phot["aperture_sum"][0]) * to_mjy
    out["err_mjy"] = float(phot["aperture_sum_err"][0]) * to_mjy
    out["ok"] = out["n_bad"] == 0 and not out["saturated"]
    if out["saturated"] or out["n_bad"] * 2 >= in_circle.sum():
        # saturated, or most of the circle masked: the sum is of zeros, not a brightness
        out["flux_mjy"] = out["err_mjy"] = np.nan
        out["flux_min_mjy"] = _lower_limit(img, x, y) * to_mjy
    return out


LIMIT_RADII_PX = (6.0, 10.0, 15.0)   # circles tried for a saturated star, smallest first


def _lower_limit(img, x, y):
    """Saturated star -> a LOWER LIMIT on its brightness (image units): the sum of the usable
    (unmasked) pixels in a wide circle, minus sky from a ring just outside it. The masked core
    counts as 0 although it holds most of the light, and light beyond the circle is left out,
    so the true brightness is higher. The circle grows until it reaches usable wings
    (R Draconis saturates more than 6 px out). NaN if no circle fits on the cutout."""
    ny, nx = img.shape
    best = np.nan
    for r in LIMIT_RADII_PX:
        r_in, r_out = r + 3, r + 7
        if not (r_out <= x < nx - r_out and r_out <= y < ny - r_out):
            break
        ring = CircularAnnulus((x, y), r_in=r_in, r_out=r_out).to_mask(method="center").to_image(img.shape)
        ring_pixels = img[ring.astype(bool) & np.isfinite(img)]
        if ring_pixels.size < 10:
            continue
        _, sky, _ = sigma_clipped_stats(ring_pixels)
        circle = CircularAperture((x, y), r=r).to_mask(method="center").to_image(img.shape).astype(bool)
        usable = circle & np.isfinite(img)
        value = float(np.sum(img[usable] - sky))
        best = value if not np.isfinite(best) else max(best, value)
        if value > 0 and usable.sum() >= 0.2 * circle.sum():
            break                                    # enough wing pixels: a meaningful limit
    return max(best, 0.0) if np.isfinite(best) else np.nan


def light_curve(frames, target, band_um, tol_um=0.02, r_px=2.0, size_deg=0.1):
    """Brightness of the target over time at ONE wavelength.
    frames table + target SkyCoord + wavelength (micron) -> Table sorted by time:
    mjd, date, wavelength_um, flux_mjy, err_mjy, flux_min_mjy, detector, n_bad, saturated, bad_flags, ok.
    Only frames where the target lands within tol_um of band_um are measured.
    flux_min_mjy: for saturated measurements only, a lower limit on the brightness."""
    lo = np.asarray(frames["em_min"], float) * 1e6 - tol_um
    hi = np.asarray(frames["em_max"], float) * 1e6 + tol_um
    rows = []
    for row in frames[(lo <= band_um) & (band_um <= hi)]:       # only detectors that cover the band
        pos = at_time(target, Time(row["mjd"], format="mjd"))
        try:
            m = measure_frame(get_cutout(row["access_url"], pos, size_deg), pos, r_px)
        except OSError as e:
            print(f"  skipped {row['obs_id']} {row['detector']}: {e}")
            continue
        if np.isfinite(m["wavelength_um"]) and abs(m["wavelength_um"] - band_um) <= tol_um:
            rows.append(m)
    names = ["mjd", "date", "wavelength_um", "flux_mjy", "err_mjy", "flux_min_mjy", "detector", "n_bad", "saturated",
             "bad_flags", "ok"]
    if not rows:
        return Table(names=names)
    t = Table(rows)
    t["date"] = Time(t["mjd"], format="mjd").iso
    t.sort("mjd")
    for col, fmt in [("wavelength_um", ".3f"), ("flux_mjy", ".2f"), ("err_mjy", ".2f"), ("flux_min_mjy", ".1f"),
                     ("mjd", ".4f")]:
        t[col].info.format = fmt
    return t[names]
