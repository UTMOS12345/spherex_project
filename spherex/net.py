"""Network helper shared by every module that talks to a server, and the demo-mode switch."""
import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from urllib.error import HTTPError

from astropy.utils.data import conf

from .progress import note_failed_try
from .text import plural

# Where downloads and saved tables live: <project>/cache, whatever folder Python was started from.
# Set SPHEREX_CACHE=/some/folder to use another one.
CACHE_ROOT = Path(os.environ.get("SPHEREX_CACHE") or Path(__file__).resolve().parent.parent / "cache")

RETRY_CODES = {429, 500, 502, 503, 504}   # "busy, try later"; 404/400 are never retried

# Demo mode (for a live presentation): no cutout downloads (frames not in cache/ are skipped),
# and every server call gets ONE try with a hard deadline, so nothing can hang the app.
DEMO_MODE = False
DEMO_DEADLINE_S = 20                      # longest any single server call may take in demo mode
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="spherex-net")


def set_demo_mode(on):
    """Switch demo mode on or off for this process (also set by SPHEREX_DEMO=1)."""
    global DEMO_MODE
    DEMO_MODE = bool(on)
    conf.remote_timeout = 8 if DEMO_MODE else 15    # seconds before a silent server counts as failed


set_demo_mode(os.environ.get("SPHEREX_DEMO", "0") == "1")


def _call(fn, args, kwargs):
    if not DEMO_MODE:
        return fn(*args, **kwargs)
    # pyvo (IRSA SIA/TAP) has no timeout of its own: wait at most DEMO_DEADLINE_S for it.
    # A call that overruns keeps running in its worker thread, but the app moves on.
    try:
        return _pool.submit(fn, *args, **kwargs).result(timeout=DEMO_DEADLINE_S)
    except FutureTimeout:
        raise TimeoutError(f"no answer within {DEMO_DEADLINE_S} s")


def with_retries(fn, *args, tries=5, **kwargs):
    """Call fn(*args, **kwargs); on network errors wait 5, 10, 20, 40, 60 s and retry.
    In demo mode: one try only, with a deadline."""
    if DEMO_MODE:
        tries = 1
    for attempt in range(tries):
        try:
            return _call(fn, args, kwargs)
        except HTTPError as e:
            if e.code not in RETRY_CODES:
                raise                                   # wrong request: retrying won't help
            err = f"HTTP {e.code}"
        except Exception as e:                          # resets, timeouts, DNS, pyvo errors
            err = f"{type(e).__name__}: {str(e)[:70]}"
        note_failed_try(err, retrying=attempt < tries - 1)   # counts for the progress line
        if attempt == tries - 1:
            raise OSError(f"{getattr(fn, '__name__', 'call')} gave up after {plural(tries, 'try', 'tries')} ({err})")
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
