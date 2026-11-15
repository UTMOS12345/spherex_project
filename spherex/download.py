"""Lesson 4 - cutouts with retries and a disk cache that never holds broken files.

Cache size (bounded cutout cache in CACHE_DIR, ``cache/cutouts`` only):
- ``SPHEREX_CACHE_MAX_GB`` (float, unset/0 = unlimited): total size cap over
  ``CACHE_DIR/*.fits``. Other cache dirs (frames/gaia/wise) are never evicted.
- ``SPHEREX_CACHE_POLICY`` (``evict`` default | ``stop``): ``evict`` removes the
  oldest cutouts (LRU by mtime) after new downloads to stay under the cap;
  ``stop`` never deletes anything and raises ``OSError`` on a cache miss when the
  cache is full (cache hits still work).
- ``SPHEREX_CACHE_TTL_DAYS`` (float, unset/0 = disabled): during a sweep, delete
  cutouts older than this many days (renew on demand; re-downloaded on next miss).
- ``SPHEREX_CACHE_SWEEP_EVERY`` (int, default 1): enforce after every N new
  downloads. All settings are read at call time; with all unset, behavior is
  unchanged (no eviction, no deletion).
"""
import os
import shutil
import threading
import time
from pathlib import Path

from astropy.io import fits
from astropy.time import Time
from astropy.utils.data import download_file

from . import net
from .net import with_retries, CACHE_ROOT
from .progress import report, DOWNLOADING
from .targets import at_time
from .text import plural

CACHE_DIR = CACHE_ROOT / "cutouts"

# Every download is at least this big (degrees). Smaller views are then made from the same
# file, so changing the field of view later never needs a new download. 0.25 deg = 15'
# (a north-up view of up to ~10' fits inside, whatever the frame's rotation).
DOWNLOAD_DEG = 0.25

# Layers dropped before saving: the PSF cube is ~5 MB per file, ~95% of a cutout, and
# nothing in this project uses it. WCS-WAVE (the wavelength map) is kept.
DROP_LAYERS = ("PSF", "EPSF")

_CACHE_LOCK = threading.RLock()
_IN_USE = set()          # paths currently in use; never evicted
_DOWNLOAD_COUNT = 0      # new-download counter for sweep cadence
_GB = 1024 ** 3

def _env_float(name, default=0.0):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default

def _cache_max_gb():
    v = _env_float("SPHEREX_CACHE_MAX_GB", 0.0)
    return v if v > 0 else 0.0

def _cache_policy():
    p = (os.environ.get("SPHEREX_CACHE_POLICY") or "evict").strip().lower()
    return p if p in ("evict", "stop") else "evict"

def _cache_ttl_days():
    v = _env_float("SPHEREX_CACHE_TTL_DAYS", 0.0)
    return v if v > 0 else 0.0

def _cache_sweep_every():
    v = _env_float("SPHEREX_CACHE_SWEEP_EVERY", 1)
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = 1
    return max(1, n)

def _cache_size_bytes():
    total = 0
    for p in CACHE_DIR.glob("*.fits"):
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total

def _enforce_cache_limit(keep=()):
    """Evict/expire cutouts in CACHE_DIR to satisfy max size and TTL (evict mode only)."""
    global _DOWNLOAD_COUNT
    max_gb = _cache_max_gb()
    ttl_days = _cache_ttl_days()
    if not max_gb and not ttl_days:
        return
    policy = _cache_policy()
    if policy != "evict":
        return
    _DOWNLOAD_COUNT += 1
    if _DOWNLOAD_COUNT % _cache_sweep_every() != 0:
        return
    keep_set = {Path(p) for p in keep}
    ttl_cutoff = time.time() - ttl_days * 86400 if ttl_days else None
    limit_bytes = int(max_gb * _GB) if max_gb else None
    evicted = 0
    evicted_bytes = 0
    with _CACHE_LOCK:
        entries = []  # (mtime, size, path)
        total = 0
        for p in CACHE_DIR.glob("*.fits"):
            try:
                st = p.stat()
            except OSError:
                continue
            entries.append((st.st_mtime, st.st_size, p))
            total += st.st_size
        entries.sort(key=lambda x: x[0])  # oldest mtime first
        for mtime, size, p in entries:
            if p in keep_set or p in _IN_USE:
                continue
            expired = ttl_cutoff is not None and mtime < ttl_cutoff
            over = limit_bytes is not None and total > limit_bytes
            if not expired and not over:
                continue
            try:
                p.unlink()
                total -= size
                evicted += 1
                evicted_bytes += size
            except OSError:
                pass
        if evicted and max_gb:
            print(f"cache {total / _GB:.1f}/{max_gb:.1f} GB: evicted {plural(evicted, 'file')} ({evicted_bytes / (1024 * 1024):.0f} MB)")
        elif evicted:
            print(f"cache: evicted {plural(evicted, 'expired file')} ({evicted_bytes / (1024 * 1024):.0f} MB)")


def cutout_url(url, center, size_deg):
    """Full-frame URL -> IRSA cutout URL (centre rounded so the cache key is stable)."""
    return f"{url}?center={center.ra.deg:.5f},{center.dec.deg:.5f}&size={size_deg}"


def cache_path(url, center, size_deg):
    """One readable file name per (frame, centre, size)."""
    frame = url.rsplit("/", 1)[-1].removesuffix(".fits")
    return CACHE_DIR / f"{frame}__{center.ra.deg:.5f}_{center.dec.deg:+.5f}_{size_deg}.fits"


def is_valid_fits(path):
    """True if the file opens and has image data (catches half-downloaded files)."""
    try:
        with fits.open(path) as h:
            return h["IMAGE"].data is not None
    except Exception:
        return False


def _download_checked(url, dest):
    """Download to a temp file, verify it, drop the unused PSF layer, then move it into the cache."""
    tmp = download_file(url, cache=False, timeout=120, show_progress=False)
    try:
        if not is_valid_fits(tmp):
            raise OSError("downloaded file is not valid FITS")
        with fits.open(tmp) as h:
            keep = fits.HDUList([hdu.copy() for hdu in h if hdu.name not in DROP_LAYERS])
            keep.writeto(str(tmp) + ".small", overwrite=True)
        shutil.move(str(tmp) + ".small", dest)
    finally:
        if os.path.exists(str(tmp) + ".small"):
            os.remove(str(tmp) + ".small")
        if os.path.exists(tmp):
            os.remove(tmp)
    return dest


def find_cached(url, center, size_deg):
    """Path of a cached cutout of this frame and centre that is at least size_deg big
    (the smallest such file), or None."""
    stem = cache_path(url, center, 0).name.rsplit("_", 1)[0]          # name without the size
    best = None
    for p in CACHE_DIR.glob(stem + "_*.fits"):
        try:
            size = float(p.stem.rsplit("_", 1)[1])
        except ValueError:
            continue
        if size >= size_deg - 1e-9 and (best is None or size < best[0]):
            best = (size, p)
    return best[1] if best else None


def get_cutout(url, center, size_deg=0.1, tries=6):
    """Frame URL + SkyCoord centre -> local path of a cutout at least size_deg big.
    Uses any cached file that is big enough; otherwise downloads max(size_deg, DOWNLOAD_DEG),
    so later requests with a different field of view are served from the same file."""
    path = find_cached(url, center, size_deg)
    if path is not None and is_valid_fits(path):
        try:
            os.utime(path)
        except OSError:
            pass
        return path
    if net.DEMO_MODE:            # callers catch OSError and skip the frame
        raise OSError("not in cache/ (demo mode: no downloads)")
    max_gb = _cache_max_gb()
    if max_gb and _cache_policy() == "stop":
        with _CACHE_LOCK:
            if _cache_size_bytes() >= int(max_gb * _GB):
                raise OSError(f"cache full ({max_gb:.1f} GB): set SPHEREX_CACHE_MAX_GB or SPHEREX_CACHE_POLICY=evict")
    fetch = max(size_deg, DOWNLOAD_DEG)
    path = cache_path(url, center, fetch)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _CACHE_LOCK:
        _IN_USE.add(path)
    try:
        result = with_retries(_download_checked, cutout_url(url, center, fetch), path, tries=tries)
    finally:
        with _CACHE_LOCK:
            _IN_USE.discard(path)
    _enforce_cache_limit(keep=(result,))
    return result


def get_cutouts(requests, progress=None):
    """Many cutouts, in order: [(url, center, size_deg), ...] -> list with, per request, the
    local path, or the OSError that get_cutout raised for it (the caller decides whether to skip).
    progress(stage, done, total) gets "downloading images" before the first and after each one
    (cached files count too)."""
    out = []
    report(progress, DOWNLOADING, 0, len(requests))
    for i, (url, center, size_deg) in enumerate(requests):
        try:
            out.append(get_cutout(url, center, size_deg))
        except OSError as e:
            out.append(e)
        report(progress, DOWNLOADING, i + 1, len(requests))
    return out


def prefetch(frames, target, size_deg=0.1, limit=None, progress=None):
    """Download cutouts for many frames, centred on the target's position on each date.
    Safe to stop and re-run: cached files are skipped. Returns (cached, downloaded, failed).
    progress: optional callback, see spherex.progress ("downloading images" per frame)."""
    hit = new = fail = 0
    rows = frames if limit is None else frames[:limit]
    report(progress, DOWNLOADING, 0, len(rows))
    for i, row in enumerate(rows):
        center = at_time(target, Time(row["mjd"], format="mjd"))
        cached = find_cached(row["access_url"], center, size_deg) is not None
        try:
            path = get_cutout(row["access_url"], center, size_deg)
            hit += cached
            new += not cached
            _enforce_cache_limit(keep=(path,))
            print(f"[{i + 1}/{len(rows)}] {'cached' if cached else 'downloaded'}  {row['date'][:10]} {row['detector']}")
        except OSError as e:
            fail += 1
            print(f"[{i + 1}/{len(rows)}] FAILED {row['obs_id']} {row['detector']}: {e}")
        report(progress, DOWNLOADING, i + 1, len(rows))
    print(f"\n{hit} cached, {new} downloaded, {fail} failed")
    return hit, new, fail


def check_cache(delete_bad=False):
    """Check every FITS file in the cache. Returns (n_valid, list_of_bad_paths).
    delete_bad=True removes broken files so the next prefetch downloads them again."""
    n_valid, bad = 0, []
    for path in sorted(CACHE_DIR.glob("*.fits")):
        if is_valid_fits(path):
            n_valid += 1
        else:
            bad.append(path)
            if delete_bad:
                path.unlink()
    return n_valid, bad
