"""Lesson 2 - turn user text into a SkyCoord (with proper motion), and time helpers."""
import re

import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astroquery.simbad import SimbadClass

J2000 = Time(51544.5, format="mjd", scale="tt")    # don't use Time("J2000"): misparsed on some versions

# Fallbacks so the challenge targets always work, even offline.
# (ra, dec) J2000 in degrees, proper motion (pmra*cos(dec), pmdec) in mas/yr.
KNOWN = {
    "barnard's star": (269.452083, 4.693391, -801.6, 10362.4),
    "wise 0855":      (133.795129, -7.245147, -8118.0, 680.0),
    "epsilon indi b": (331.04383, -56.78269, 3966.7, -2536.2),
    "rw aur":         (76.95641, 30.40142, 0.0, 0.0),
    "rw aurigae":     (76.95641, 30.40142, 0.0, 0.0),
    "r dra":          (248.16738, 66.75503, 0.0, 0.0),
    "r draconis":     (248.16738, 66.75503, 0.0, 0.0),
}
SIMBAD_SERVERS = ["simbad.harvard.edu", "simbad.cds.unistra.fr"]   # Harvard first: CDS is blocked for us


def make_coord(ra, dec, pmra=None, pmdec=None):
    """SkyCoord at epoch J2000; carries proper motion if it is known and non-zero."""
    if pmra is None or pmdec is None or (pmra == 0 and pmdec == 0):
        return SkyCoord(ra * u.deg, dec * u.deg)
    return SkyCoord(ra * u.deg, dec * u.deg, obstime=J2000,
                    pm_ra_cosdec=pmra * u.mas / u.yr, pm_dec=pmdec * u.mas / u.yr)


def has_pm(coord):
    """True if the SkyCoord carries a proper motion."""
    return bool(coord.data.differentials)


def at_time(coord, t):
    """Position at astropy Time t, returned WITHOUT velocities (safe for WCS and cutouts)."""
    c = coord.apply_space_motion(new_obstime=t) if has_pm(coord) else coord
    return SkyCoord(c.ra, c.dec)


def years_since_j2000(t):
    """astropy Time -> years since J2000 (Quantity)."""
    return (t - J2000).to(u.yr)


def _simbad_for(server):
    # add_votable_fields contacts the server, so set the mirror first
    s = SimbadClass()
    s.server = server
    s.add_votable_fields("pmra", "pmdec")
    return s


def _num(v):
    return None if np.ma.is_masked(v) else float(v)


def resolve_name(name):
    """Name -> SkyCoord. SIMBAD (Harvard, then CDS), built-in list, then Sesame."""
    for server in SIMBAD_SERVERS:
        try:
            r = _simbad_for(server).query_object(name)
            if r is not None and len(r) > 0:
                return make_coord(float(r["ra"][0]), float(r["dec"][0]),
                                  _num(r["pmra"][0]), _num(r["pmdec"][0]))
        except Exception as e:
            print(f"  SIMBAD {server} failed: {type(e).__name__}")
    key = name.strip().lower()
    if key in KNOWN:
        print("  using built-in position + proper motion")
        return make_coord(*KNOWN[key])
    try:
        return SkyCoord.from_name(name)          # position only, no proper motion
    except Exception as e:
        print(f"  Sesame failed: {type(e).__name__}")
    raise ValueError(f"Could not resolve name: {name!r}")


def parse_target(text):
    """User text -> SkyCoord. Accepts '269.45 4.69' (degrees), '17h57m48.5s +04d41m36s',
    '17:57:48.5 +04:41:36', '17 57 48.5 +04 41 36' (RA in hours), or an object name."""
    text = text.strip()
    if re.fullmatch(r"[+-]?\d+(\.\d*)?[\s,]+[+-]?\d+(\.\d*)?", text):     # two plain numbers
        ra, dec = re.split(r"[\s,]+", text)
        return SkyCoord(float(ra), float(dec), unit="deg")
    if text[:1].isdigit():                       # don't test for h/m/s/d: names contain them
        try:
            return SkyCoord(text, unit=(u.hourangle, u.deg))
        except ValueError:
            pass                                 # e.g. "2MASS J0855..." is a name
    return resolve_name(text)
