"""Network helper shared by every module that talks to a server."""
import time
from urllib.error import HTTPError

from astropy.utils.data import conf

conf.remote_timeout = 15            # seconds before a silent server counts as failed

RETRY_CODES = {429, 500, 502, 503, 504}   # "busy, try later"; 404/400 are never retried


def with_retries(fn, *args, tries=5, **kwargs):
    """Call fn(*args, **kwargs); on network errors wait 5, 10, 20, 40, 60 s and retry."""
    for attempt in range(tries):
        try:
            return fn(*args, **kwargs)
        except HTTPError as e:
            if e.code not in RETRY_CODES:
                raise                                   # wrong request: retrying won't help
            err = f"HTTP {e.code}"
        except Exception as e:                          # resets, timeouts, DNS, pyvo errors
            err = f"{type(e).__name__}: {str(e)[:70]}"
        if attempt == tries - 1:
            raise OSError(f"{getattr(fn, '__name__', 'call')} gave up after {tries} tries ({err})")
        wait = min(5 * 2 ** attempt, 60)
        print(f"    {getattr(fn, '__name__', 'call')}: {err} -> retry in {wait}s")
        time.sleep(wait)


CONE_SLACK_DEG = 0.002     # 7": file names round the centre to 4 decimals (0.36"), and the
                           # view centre of a fast mover shifts a few arcsec after a refresh.
                           # Missing a 7" sliver at the edge of a 9' circle does not matter.


def find_cached_cone(folder, prefix, center, radius_deg):
    """A cached catalogue file (folder/prefix_<ra>_<dec>_<radius>.ecsv) whose circle
    contains the requested one (within CONE_SLACK_DEG) -> its rows inside the requested
    circle; else None."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astropy.table import Table
    import numpy as np
    for p in sorted(folder.glob(f"{prefix}_*.ecsv")):
        try:
            ra, dec, rad = (float(v) for v in p.stem[len(prefix) + 1:].split("_"))
        except ValueError:
            continue
        if center.separation(SkyCoord(ra * u.deg, dec * u.deg)).deg + radius_deg <= rad + CONE_SLACK_DEG:
            t = Table.read(p)
            sep = center.separation(SkyCoord(np.asarray(t["ra"], float) * u.deg, np.asarray(t["dec"], float) * u.deg))
            return t[sep.deg <= radius_deg]
    return None
