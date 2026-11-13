"""Lesson 8 - Gaia DR3 stars around the target, moved to any date, drawn on the image."""
from pathlib import Path

import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time

from .net import with_retries, find_cached_cone

GAIA_DIR = Path("cache/gaia")
GAIA_EPOCH = Time(2016.0, format="jyear")        # Gaia DR3 positions are for the year 2016.0
COLUMNS = "source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag"


def _from_irsa(center, radius_deg):
    """Gaia DR3 from IRSA's copy of the catalogue (same server as the SPHEREx data)."""
    from astroquery.ipac.irsa import Irsa
    q = (f"SELECT {COLUMNS} FROM gaia_dr3_source WHERE CONTAINS(POINT('ICRS', ra, dec), "
         f"CIRCLE('ICRS', {center.ra.deg:.6f}, {center.dec.deg:.6f}, {radius_deg:.5f})) = 1")
    return Table(Irsa.query_tap(q).to_table())


def _from_esa(center, radius_deg):
    """Gaia DR3 from ESA's own Gaia archive."""
    from astroquery.gaia import Gaia
    q = (f"SELECT {COLUMNS} FROM gaiadr3.gaia_source WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), "
         f"CIRCLE('ICRS', {center.ra.deg:.6f}, {center.dec.deg:.6f}, {radius_deg:.5f}))")
    return Table(Gaia.launch_job(q).get_results())


def gaia_stars(center, radius_deg=0.08):
    """Cone search in Gaia DR3 -> Table (source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag).
    Positions are for 2016.0. Saved to cache/gaia/, so each field is downloaded once."""
    cached = find_cached_cone(GAIA_DIR, "gaia", center, radius_deg)   # any bigger saved circle works
    if cached is not None:
        return cached
    path = GAIA_DIR / f"gaia_{center.ra.deg:.4f}_{center.dec.deg:+.4f}_{radius_deg:.3f}.ecsv"
    last = None
    for source in (_from_irsa, _from_esa):
        try:
            t = with_retries(source, center, radius_deg, tries=3)
            t = Table({c: np.ma.filled(np.ma.asarray(t[c], dtype=float), np.nan) if c != "source_id"
                       else np.asarray(t[c]).astype(str) for c in t.colnames})    # plain columns
            GAIA_DIR.mkdir(parents=True, exist_ok=True)
            t.write(path, overwrite=True)
            return t
        except Exception as e:
            last = e
            print(f"  Gaia via {source.__name__[6:].upper()} failed: {type(e).__name__}: {str(e)[:80]}")
    raise OSError(f"Gaia query failed on both servers ({last})")


def gaia_overlay(center, radius_deg, t):
    """Gaia DR3 stars around `center`, with each star moved to where it is at Time t.
    Adds columns: ra_t, dec_t (degrees, at time t) and pm_total (mas/yr)."""
    stars = gaia_stars(center, radius_deg)
    if len(stars) == 0:              # e.g. no CatWISE source in a bright star's halo
        stars = stars.copy()
        for col in ("ra_t", "dec_t", "pm_total"):
            stars[col] = np.zeros(0)
        return stars
    pmra = np.nan_to_num(np.asarray(stars["pmra"], float))       # no proper motion known -> 0
    pmdec = np.nan_to_num(np.asarray(stars["pmdec"], float))
    c = SkyCoord(np.asarray(stars["ra"], float) * u.deg, np.asarray(stars["dec"], float) * u.deg,
                 pm_ra_cosdec=pmra * u.mas / u.yr, pm_dec=pmdec * u.mas / u.yr, obstime=GAIA_EPOCH)
    moved = c.apply_space_motion(new_obstime=t)
    stars = stars.copy()
    stars["ra_t"] = moved.ra.deg
    stars["dec_t"] = moved.dec.deg
    stars["pm_total"] = np.hypot(pmra, pmdec)
    return stars


def draw_gaia(ax, stars, wcs, shape, min_pm=50, arrow_years=5, color="cyan", fast_color="yellow",
              marker="o", min_snr=5):
    """Draw catalogue stars (Gaia, or WISE from wise.py) on a matplotlib image axis.
    Needs columns ra_t, dec_t (deg, at time t), pmra, pmdec, pm_total (mas/yr).
    Every star: small marker at its position at time t.
    Stars faster than min_pm (mas/yr): bigger marker + arrow showing where they will be
    arrow_years later. If the table has a pm_snr column (WISE), a star also needs
    pm_snr >= min_snr to count as fast, so noisy catalogue motions get no arrow.
    Returns how many stars fell on the image."""
    ny, nx = shape
    pos = SkyCoord(stars["ra_t"] * u.deg, stars["dec_t"] * u.deg)
    x, y = wcs.world_to_pixel(pos)
    on = (x >= 0) & (x < nx) & (y >= 0) & (y < ny)
    fast = on & (np.asarray(stars["pm_total"]) >= min_pm)
    if "pm_snr" in stars.colnames:
        fast &= np.asarray(stars["pm_snr"], float) >= min_snr
    ax.scatter(x[on & ~fast], y[on & ~fast], s=40, marker=marker, facecolors="none", edgecolors=color, lw=0.6)
    ax.scatter(x[fast], y[fast], s=160, marker=marker, facecolors="none", edgecolors=fast_color, lw=1.2)
    for row, x0, y0 in zip(stars[fast], x[fast], y[fast]):
        # where will it be arrow_years later? (north-up grid: +RA is to the left)
        d_ra = np.nan_to_num(row["pmra"]) / 1000 * arrow_years / 3600 / np.cos(np.deg2rad(row["dec_t"]))
        d_dec = np.nan_to_num(row["pmdec"]) / 1000 * arrow_years / 3600
        x1, y1 = wcs.world_to_pixel(SkyCoord((row["ra_t"] + d_ra) * u.deg, (row["dec_t"] + d_dec) * u.deg))
        ax.annotate("", xy=(float(x1), float(y1)), xytext=(float(x0), float(y0)),
                    arrowprops=dict(arrowstyle="->", color=fast_color, lw=1.5), annotation_clip=False)
    ax.set_xlim(-0.5, nx - 0.5); ax.set_ylim(-0.5, ny - 0.5)
    return int(on.sum())
