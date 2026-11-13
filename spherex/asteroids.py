"""Known asteroids and comets in the field (IMCCE SkyBoT service, through astroquery).

SkyBoT computes, for any position and date, which known solar-system objects are there.
The server is in France and may be unreachable on some networks: callers should treat a
failure as "overlay not available", not as "no asteroids".
"""
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

from .net import with_retries


def known_asteroids(center, radius_deg, t):
    """Known solar-system objects within radius_deg of center at Time t ->
    Table (name, type, ra, dec, v_mag); empty table when there are none."""
    from astroquery.imcce import Skybot
    def search():
        try:
            return Skybot.cone_search(center, radius_deg * u.deg, t)
        except RuntimeError as e:          # "No solar system object was found": an answer, not a failure
            if "no solar system object" in str(e).lower() or "no object" in str(e).lower():
                return None
            raise
    res = with_retries(search, tries=2)
    if res is None:
        return Table(names=["name", "type", "ra", "dec", "v_mag"], dtype=[str, str, float, float, float])
    cols = {c.lower(): c for c in res.colnames}
    ra = np.asarray(u.Quantity(res[cols["ra"]]).to(u.deg).value, float)
    dec = np.asarray(u.Quantity(res[cols["dec"]]).to(u.deg).value, float)
    vmag = np.asarray(res[cols["v"]], float) if "v" in cols else np.full(len(res), np.nan)
    return Table({"name": [str(x) for x in res[cols["name"]]],
                  "type": [str(x) for x in res[cols.get("type", cols["name"])]],
                  "ra": ra, "dec": dec, "v_mag": vmag})


def draw_asteroids(ax, objects, wcs, shape):
    """Green-yellow diamonds + names for known asteroids/comets. Returns how many are on the image."""
    if len(objects) == 0:
        return 0
    ny, nx = shape
    x, y = wcs.world_to_pixel(SkyCoord(objects["ra"] * u.deg, objects["dec"] * u.deg))
    on = (x >= 0) & (x < nx) & (y >= 0) & (y < ny)
    ax.scatter(x[on], y[on], s=120, marker="D", facecolors="none", edgecolors="#c8e34a", lw=1.2)
    for name, xi, yi in zip(objects["name"][on], x[on], y[on]):
        ax.annotate(name, (xi, yi), xytext=(6, 6), textcoords="offset points", fontsize=8, color="#c8e34a")
    return int(on.sum())
