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
