"""WISE overlay - CatWISE2020 sources around the target, moved to any date.

CatWISE2020 is built from ~8 years of WISE/NEOWISE images (3.4 and 4.6 micron), so it
measures proper motions even for objects too cold for Gaia, such as brown dwarfs.
Facts used here (CatWISE2020 documentation at IRSA):
  * ra_pm, dec_pm = position at epoch MJD 57170 (2015 May 28), including the motion fit
  * pmra, pmdec   = motion in arcsec/yr (converted to mas/yr below)
  * sigpmra, sigpmdec = uncertainty of that motion (arcsec/yr)
  * ab_flags, cc_flags = artefact flags (unWISE, AllWISE); '0's mean clean
  * w1mpro, w2mpro = brightness at 3.4 and 4.6 micron (magnitudes)
CatWISE motions of faint sources are noisy (errors of 50-100+ mas/yr), so only motions
measured at PM_SNR_MIN sigma or better, on sources with no artefact flag, count as real
(column pm_snr; 0 for flagged sources). Halos and spikes of saturated stars (Barnard's Star)
otherwise give hundreds of fake 'significant' motions.
"""
from pathlib import Path

import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time

from . import net
from .net import with_retries, find_cached_cone

WISE_DIR = Path("cache/wise")
CATWISE_EPOCH = Time(57170.0, format="mjd")
CATWISE_TABLE = "catwise_2020"
PM_SNR_MIN = 5                 # motion / its uncertainty needed before a WISE arrow is drawn
OLD_CACHE_MIN_PM = 300         # cache files without sigpm*: only motions above this count


def wise_stars(center, radius_deg=0.08):
    """CatWISE2020 cone search -> Table (source_name, ra, dec at 2015.4, pmra, pmdec in mas/yr,
    w1mpro, w2mpro). Saved to cache/wise/, so each field is downloaded once."""
    cached = find_cached_cone(WISE_DIR, "catwise", center, radius_deg)   # any bigger saved circle works
    # files saved before the motion uncertainties were kept are used only when we can't ask the server
    if cached is not None and ("ab_flags" in cached.colnames or net.DEMO_MODE):
        return cached
    path = WISE_DIR / f"catwise_{center.ra.deg:.4f}_{center.dec.deg:+.4f}_{radius_deg:.3f}.ecsv"
    from astroquery.ipac.irsa import Irsa
    q = (f"SELECT source_name, ra_pm, dec_pm, pmra, pmdec, sigpmra, sigpmdec, ab_flags, cc_flags, w1mpro, w2mpro FROM {CATWISE_TABLE} "
         f"WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {center.ra.deg:.6f}, "
         f"{center.dec.deg:.6f}, {radius_deg:.5f})) = 1")
    t = Table(with_retries(lambda: Irsa.query_tap(q).to_table(), tries=3))
    t = {c.lower(): t[c] for c in t.colnames}                  # column-name case varies
    num = lambda c: np.ma.filled(np.ma.asarray(t[c], dtype=float), np.nan)
    out = Table({"source_name": np.asarray(t["source_name"]).astype(str),
                 "ra": num("ra_pm"), "dec": num("dec_pm"),
                 "pmra": num("pmra") * 1000, "pmdec": num("pmdec") * 1000,     # arcsec/yr -> mas/yr
                 "sigpmra": num("sigpmra") * 1000, "sigpmdec": num("sigpmdec") * 1000,
                 "ab_flags": np.asarray(np.ma.filled(t["ab_flags"], "")).astype(str),
                 "cc_flags": np.asarray(np.ma.filled(t["cc_flags"], "")).astype(str),
                 "w1mpro": num("w1mpro"), "w2mpro": num("w2mpro")})
    WISE_DIR.mkdir(parents=True, exist_ok=True)
    out.write(path, overwrite=True)
    return out


def wise_overlay(center, radius_deg, t):
    """CatWISE2020 sources around `center`, each moved to where it is at Time t.
    Adds columns ra_t, dec_t (degrees) and pm_total (mas/yr) - same layout as gaia_overlay,
    so draw_gaia() can draw both."""
    stars = wise_stars(center, radius_deg)
    if len(stars) == 0:              # e.g. no CatWISE source in a bright star's halo
        stars = stars.copy()
        for col in ("ra_t", "dec_t", "pm_total", "pm_snr"):
            stars[col] = np.zeros(0)
        return stars
    pmra = np.nan_to_num(np.asarray(stars["pmra"], float))
    pmdec = np.nan_to_num(np.asarray(stars["pmdec"], float))
    c = SkyCoord(np.asarray(stars["ra"], float) * u.deg, np.asarray(stars["dec"], float) * u.deg,
                 pm_ra_cosdec=pmra * u.mas / u.yr, pm_dec=pmdec * u.mas / u.yr, obstime=CATWISE_EPOCH)
    moved = c.apply_space_motion(new_obstime=t)
    stars = stars.copy()
    stars["ra_t"] = moved.ra.deg
    stars["dec_t"] = moved.dec.deg
    stars["pm_total"] = np.hypot(pmra, pmdec)
    if "sigpmra" in stars.colnames:
        err = np.hypot(np.asarray(stars["sigpmra"], float), np.asarray(stars["sigpmdec"], float))
        stars["pm_snr"] = np.nan_to_num(stars["pm_total"] / np.where(err > 0, err, np.nan))
        if "ab_flags" in stars.colnames:
            text = lambda col: ["" if np.ma.is_masked(v) else str(v).strip() for v in stars[col]]  # "" = no flag
            clean = np.array([set(a) <= {"0"} and set(c) <= {"0"}
                              for a, c in zip(text("ab_flags"), text("cc_flags"))], bool)
            stars["pm_snr"] = np.where(clean, stars["pm_snr"], 0.0)
    else:                      # old cache file without uncertainties: trust only big motions
        stars["pm_snr"] = np.where(stars["pm_total"] >= OLD_CACHE_MIN_PM, np.inf, 0.0)
    return stars
