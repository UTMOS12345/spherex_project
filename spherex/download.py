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

Parallel downloads: ``SPHEREX_DOWNLOAD_WORKERS`` (int, default 6) cutouts are fetched at
once by get_cutouts and prefetch. Results, their order and the file names do not depend on
it; 1 downloads one after another. Each file is written to a temporary name next to its
final place and renamed, so the cache never holds a half-written file.
"""
import contextvars
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from astropy.io import fits
from astropy.utils.data import download_file

from . import net
from .net import with_retries, CACHE_ROOT
from .progress import report, DOWNLOADING
from .targets import at_times
from .text import plural

CACHE_DIR = CACHE_ROOT / "cutouts"

# Every download is at least this big (degrees). Smaller views are then made from the same
# file, so changing the field of view later never needs a new download. 0.25 deg = 15'
# (a north-up view of up to ~10' fits inside, whatever the frame's rotation).
DOWNLOAD_DEG = 0.25

# Layers dropped before saving: the PSF cube (EPSF in DR1 files) is ~4 MB per file, over 90% of
# a cutout, and nothing in this project uses it. WCS-WAVE (the wavelength map) is kept.
# IRSA's cutout service cannot leave it out: it takes only center= and size=, cuts every image
# layer and returns the PSF whole (checked 16 Nov 2026: ext=, hdu=, extension=, exclude= are
# ignored, 4.37 MB each; gzip=true saves 9%). So it is downloaded, then stripped here.
DROP_LAYERS = ("PSF", "EPSF")

_CACHE_LOCK = threading.RLock()
_IN_USE = set()          # paths currently in use; never evicted
_DOWNLOAD_COUNT = 0      # new-download counter for sweep cadence
_GB = 1024 ** 3
DEFAULT_WORKERS = 6


def download_workers():
    """How many cutouts to download at once (SPHEREX_DOWNLOAD_WORKERS, default 6, at least 1)."""
    try:
        return max(1, int(os.environ.get("SPHEREX_DOWNLOAD_WORKERS") or DEFAULT_WORKERS))
    except ValueError:
        return DEFAULT_WORKERS

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
    with _CACHE_LOCK:                 # downloads finish on several threads at once
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
    """Download to a temp file, verify it, drop the unused PSF layer, write the result to a
    temporary name in the cache folder and rename it into place (atomic on one file system:
    readers see either no file or the whole file, also with several downloads at once)."""
    tmp = download_file(url, cache=False, timeout=120, show_progress=False)
    part = dest.with_name(f".{dest.name}.{os.getpid()}.{threading.get_ident()}.part")
    try:
        if not is_valid_fits(tmp):
            raise OSError("downloaded file is not valid FITS")
        with fits.open(tmp) as h:
            keep = fits.HDUList([hdu.copy() for hdu in h if hdu.name not in DROP_LAYERS])
            keep.writeto(part, overwrite=True)
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            os.remove(part)
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


def _get_or_error(url, center, size_deg):
    try:
        return get_cutout(url, center, size_deg)
    except OSError as e:
        return e


def _fetch_all(jobs, workers, on_done):
    """Run _get_or_error for every job [(key, (url, center, size_deg))], up to `workers` at
    once. on_done(key, result) runs on the CALLING thread as each one finishes, so progress
    callbacks (Streamlit) never run on a worker thread."""
    if workers <= 1 or len(jobs) <= 1:
        for key, args in jobs:
            on_done(key, _get_or_error(*args))
        return
    with ThreadPoolExecutor(max_workers=min(workers, len(jobs)), thread_name_prefix="spherex-dl") as pool:
        futures = {pool.submit(_get_or_error, *args): key for key, args in jobs}
        for fut in as_completed(futures):
            on_done(futures[fut], fut.result())


_COUNTING = contextvars.ContextVar("spherex_counting_downloads", default=False)


class DownloadCount(BaseException):
    """Raised by get_cutouts inside counting(): the call stops before downloading anything.
    missing: files it would download; total: images it asked for. A BaseException, so the
    `except Exception` blocks of the callers do not swallow it."""

    def __init__(self, missing, total):
        super().__init__(f"{missing} of {total} images to download")
        self.missing, self.total = missing, total


class counting:
    """with counting(): ... -> the first get_cutouts call raises DownloadCount instead of
    downloading or reading any image (for "this needs N images" before a long call)."""

    def __enter__(self):
        self._token = _COUNTING.set(True)
        return self

    def __exit__(self, *exc):
        _COUNTING.reset(self._token)
        return False


_MISSING = contextvars.ContextVar("spherex_missing_images", default=None)


class track_missing:
    """with track_missing() as t: ... -> t.count = images that get_cutouts could not supply
    (not in the cache offline, or failed) during the block. spherex.results saves a result only
    when this is 0."""

    def __init__(self):
        self.count = 0

    def __enter__(self):
        self._token = _MISSING.set(self)
        return self

    def __exit__(self, *exc):
        _MISSING.reset(self._token)
        return False


def note_missing(n):
    """Add n missing images to the active track_missing block, if any."""
    t = _MISSING.get()
    if t is not None:
        t.count += n


def _touch(path):
    try:
        os.utime(path)                 # most recently used: the cutout cache evicts it last
    except OSError:
        pass


def get_cutouts(requests, progress=None, workers=None, trusted=None):
    """Many cutouts: [(url, center, size_deg), ...] -> list in the same order with, per request,
    the local path, or the OSError that get_cutout raised for it (the caller decides whether to
    skip). Cached files are looked up first; the rest are downloaded `workers` at a time
    (default download_workers()); a request repeated in the list is downloaded once.
    trusted: optional callable(path) -> bool. A cached file it returns True for is used without
    opening it to check it (is_valid_fits); the caller vouches for its content (the stacker:
    the frame cache already holds this file's result, keyed by a hash of its bytes).
    progress(stage, done, total) gets "downloading images" before the first and after each one
    (cached files count too)."""
    total = len(requests)
    out = [None] * total
    done = 0
    local, missing = [], {}                        # missing: cache file name -> request indices
    found = {}                                     # request index -> cached path
    for i, (url, center, size_deg) in enumerate(requests):
        path = find_cached(url, center, size_deg) if (trusted is not None or not net.DEMO_MODE) else None
        if path is not None:
            found[i] = path
        if net.DEMO_MODE or path is not None:
            local.append(i)
        else:
            missing.setdefault(cache_path(url, center, max(size_deg, DOWNLOAD_DEG)).name, []).append(i)
    if _COUNTING.get():
        raise DownloadCount(len(missing), total)
    report(progress, DOWNLOADING, 0, total)
    for i in local:                                # no network: answer at once
        path = found.get(i)
        if path is not None and trusted is not None:
            _touch(path)                           # before hashing: the hash is remembered per mtime
            if trusted(path):
                out[i] = path
                done += 1
                report(progress, DOWNLOADING, done, total)
                continue
        out[i] = _get_or_error(*requests[i])
        done += 1
        report(progress, DOWNLOADING, done, total)

    def finished(indices, result):
        nonlocal done
        for i in indices:
            out[i] = result
            done += 1
            report(progress, DOWNLOADING, done, total)
    jobs = [(tuple(ix), requests[ix[0]]) for ix in missing.values()]
    _fetch_all(jobs, download_workers() if workers is None else workers, finished)
    note_missing(sum(isinstance(r, OSError) for r in out))
    return out


def prefetch(frames, target, size_deg=0.1, limit=None, progress=None, workers=None):
    """Download cutouts for many frames, centred on the target's position on each date,
    `workers` at a time (default download_workers()).
    Safe to stop and re-run: cached files are skipped. Returns (cached, downloaded, failed).
    progress: optional callback, see spherex.progress ("downloading images" per frame)."""
    hit = new = fail = n = 0
    rows = frames if limit is None else frames[:limit]
    report(progress, DOWNLOADING, 0, len(rows))
    jobs = []
    for i, (row, center) in enumerate(zip(rows, at_times(target, rows["mjd"]))):
        cached = find_cached(row["access_url"], center, size_deg) is not None
        jobs.append(((i, cached), (row["access_url"], center, size_deg)))

    def finished(key, result):
        nonlocal hit, new, fail, n
        i, cached = key
        row = rows[i]
        n += 1
        if isinstance(result, OSError):
            fail += 1
            print(f"[{n}/{len(rows)}] FAILED {row['obs_id']} {row['detector']}: {result}")
        else:
            hit += cached
            new += not cached
            _enforce_cache_limit(keep=(result,))
            print(f"[{n}/{len(rows)}] {'cached' if cached else 'downloaded'}  {row['date'][:10]} {row['detector']}")
        report(progress, DOWNLOADING, n, len(rows))
    _fetch_all(jobs, download_workers() if workers is None else workers, finished)
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
