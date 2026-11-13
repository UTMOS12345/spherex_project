"""Lesson 2 - turn user text into a SkyCoord (with proper motion), and time helpers."""
import re

import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astroquery.simbad import SimbadClass

J2000 = Time(51544.5, format="mjd", scale="tt")    # don't use Time("J2000"): misparsed on some versions

# Fallbacks so the challenge targets always work, even offline.
# (ra, dec) in degrees, proper motion (pmra*cos(dec), pmdec) in mas/yr, and the EPOCH (year)
# the position refers to. The epoch matters for fast movers: WISE 0855's position is the WISE
# measurement from ~2010.4 (its name WISE J085510.83-071442.5 encodes it), not a year-2000
# position - treating it as 2000 put the prediction ~85" (14 pixels) too far west in 2026.
# The Epsilon Indi B epoch has not been checked against a catalogue.
KNOWN = {
    "barnard's star": (269.452083, 4.693391, -801.6, 10362.4, 2000.0),
    "wise 0855":      (133.795129, -7.245147, -8118.0, 680.0, 2010.4),
    "epsilon indi b": (331.04383, -56.78269, 3966.7, -2536.2, 2000.0),
    "rw aur":         (76.95641, 30.40142, 0.0, 0.0, 2000.0),
    "r dra":          (248.16738, 66.75503, 0.0, 0.0, 2000.0),
}
ALIASES = {
    "barnard": "barnard's star", "barnards star": "barnard's star", "gj 699": "barnard's star",
    "wise j085510.83-071442.5": "wise 0855", "wise j0855-0714": "wise 0855", "wise 0855-0714": "wise 0855",
    "eps ind b": "epsilon indi b", "eps indi b": "epsilon indi b", "epsilon indi ba": "epsilon indi b",
    "rw aurigae": "rw aur", "r draconis": "r dra",
}
MATCH_RADIUS = 10 * u.arcsec     # typed coordinates this close to a KNOWN target get its motion

# One display name per KNOWN target. It is also the name of its cache files
# (cache/frames/<name>.ecsv), whatever alias or coordinates the user typed.
DISPLAY = {"barnard's star": "Barnard's Star", "wise 0855": "WISE 0855",
           "epsilon indi b": "Epsilon Indi B", "rw aur": "RW Aur", "r dra": "R Draconis"}


def known_target(name):
    """Name -> KNOWN key, or None."""
    key = " ".join(name.strip().lower().split())
    key = ALIASES.get(key, key)
    return key if key in KNOWN else None


def known_near(coord):
    """KNOWN key of the target within MATCH_RADIUS of `coord`, either at its catalogue
    position or at where it is today (fast movers are far from their catalogue position), or None."""
    now = Time.now()
    for key, row in KNOWN.items():
        known = make_coord(*row)
        if (coord.separation(SkyCoord(row[0] * u.deg, row[1] * u.deg)) < MATCH_RADIUS or
                coord.separation(at_time(known, now)) < MATCH_RADIUS):
            return key
    return None


def target_name(text, coord=None):
    """The one name used for a target's cache files: the display name of a KNOWN target
    (found by name, alias, or coordinates close to it), else the text as typed, with
    spacing and letter case normalised."""
    key = known_target(text) or (known_near(coord) if coord is not None else None)
    return DISPLAY[key] if key else re.sub(r"\s+", " ", text.strip().lower())


SIMBAD_SERVERS = ["simbad.harvard.edu", "simbad.cds.unistra.fr"]   # Harvard first: CDS is blocked for us


def make_coord(ra, dec, pmra=None, pmdec=None, epoch=2000.0):
    """SkyCoord whose position refers to the year `epoch` (default 2000.0);
    carries proper motion if it is known and non-zero."""
    if pmra is None or pmdec is None or (pmra == 0 and pmdec == 0):
        return SkyCoord(ra * u.deg, dec * u.deg)
    obstime = J2000 if epoch == 2000.0 else Time(epoch, format="jyear")
    return SkyCoord(ra * u.deg, dec * u.deg, obstime=obstime,
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
    """Name -> SkyCoord. The challenge targets come from KNOWN (position, motion and epoch
    checked); other names from SIMBAD (Harvard, then CDS), then Sesame."""
    key = known_target(name)
    if key:
        return make_coord(*KNOWN[key])
    for server in SIMBAD_SERVERS:
        try:
            r = _simbad_for(server).query_object(name)
            if r is not None and len(r) > 0:
                return make_coord(float(r["ra"][0]), float(r["dec"][0]),
                                  _num(r["pmra"][0]), _num(r["pmdec"][0]))
        except Exception as e:
            print(f"  SIMBAD {server} failed: {type(e).__name__}")
    try:
        return SkyCoord.from_name(name)          # position only, no proper motion
    except Exception as e:
        print(f"  Sesame failed: {type(e).__name__}")
    raise ValueError(f"Could not resolve name: {name!r}")


def attach_known_motion(coord):
    """Typed coordinates within MATCH_RADIUS of a KNOWN target -> that target, with its
    proper motion and epoch (typed coordinates carry no motion by themselves)."""
    key = known_near(coord)
    if key is None or (KNOWN[key][2] == 0 and KNOWN[key][3] == 0):
        return coord
    print(f"  coordinates match {key!r}: using its proper motion (epoch {KNOWN[key][4]})")
    return make_coord(*KNOWN[key])


def parse_target(text):
    """User text -> SkyCoord. Accepts '269.45 4.69' (degrees), '17h57m48.5s +04d41m36s',
    '17:57:48.5 +04:41:36', '17 57 48.5 +04 41 36' (RA in hours), or an object name."""
    text = text.strip()
    if re.fullmatch(r"[+-]?\d+(\.\d*)?[\s,]+[+-]?\d+(\.\d*)?", text):     # two plain numbers
        ra, dec = re.split(r"[\s,]+", text)
        return attach_known_motion(SkyCoord(float(ra), float(dec), unit="deg"))
    if text[:1].isdigit():                       # don't test for h/m/s/d: names contain them
        try:
            return attach_known_motion(SkyCoord(text, unit=(u.hourangle, u.deg)))
        except ValueError:
            pass                                 # e.g. "2MASS J0855..." is a name
    return resolve_name(text)
