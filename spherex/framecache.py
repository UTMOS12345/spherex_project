"""Frame cache: each frame cleaned and reprojected onto a view's grid, kept on disk.

Building a view cleans every frame (Lesson 5), levels it to zero sky and reprojects it onto the
view's sky grid (epochs._aligned_layer). The result depends only on the cutout file, the
cleaning settings and the grid, so it is the same for every view that uses that frame on that
grid: clip on or off, every time step, every visit pair, deep image or difference. This module
keeps those aligned frames under <cache>/frames_proc/, so a second view that shares them skips
the work.

What is stored: exactly the array the stacker uses (float64, NaN = no value), as one plain
uncompressed .npy file per frame and grid. Kept as float64, not float32, so the stacks stay
byte-identical with and without this cache. A frame that never sees a requested wavelength
range is stored as an empty array (shape (0,)), so that answer is cached too.

The key (sha256 of a JSON payload, as in spherex.results) covers everything that changes the
array: the cutout's CONTENT (sha256 of the file: get_cutout touches a file's mtime on every use,
so path + mtime would never match), bad_flags, keep_saturated_stars, bloom_radius, wl_range,
the grid (WCS parameters at full float precision, and the shape), FRAME_CACHE_VERSION and the
versions of numpy, scipy, astropy and reproject. The WCS is never stored: the caller always
passes the grid it built (epochs.epoch_grid), so a loaded frame cannot carry a WCS that is
1e-12 deg off.

Writes go to a temporary name in the same folder and are renamed into place (atomic), so
threads or processes working on the same frame at once each write a whole file and the last
rename wins; readers see the whole file or none. Only a finished array is written: an
exception while cleaning or reprojecting stores nothing. A file that cannot be read counts as
a miss and is recomputed.

Settings (read at call time):
- SPHEREX_FRAME_CACHE=0 turns the cache off (no reads, no writes).
- SPHEREX_FRAME_CACHE_MAX_GB (float, default 2; 0 = unlimited): size cap. After new entries
  are written, the least recently used ones (oldest mtime; a hit renews it) are deleted until
  the folder is under the cap.
- SPHEREX_CACHE_TTL_DAYS (shared with the cutout cache): entries unused for that long go too.
The cutout settings SPHEREX_CACHE_MAX_GB / SPHEREX_CACHE_POLICY apply to cutouts only: these
files can always be recomputed, so this cache never refuses to grow, it evicts.
"""
import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path

import numpy as np

from .net import CACHE_ROOT

FRAME_CACHE_VERSION = 1          # raise when a code change alters any aligned frame
FRAME_DIR = CACHE_ROOT / "frames_proc"
DEFAULT_MAX_GB = 2.0
SWEEP_EVERY = 64                 # new entries between size checks (and after every view)
_GB = 1024 ** 3

_lock = threading.Lock()
_digests = {}                    # (path, inode, size, mtime_ns) -> sha256 of the file
_writes = 0                      # entries written since the last sweep


def enabled():
    """False when SPHEREX_FRAME_CACHE=0 (or 'false', 'no', 'off')."""
    return (os.environ.get("SPHEREX_FRAME_CACHE") or "1").strip().lower() not in ("0", "false", "no", "off")


def _env_float(name, default):
    try:
        v = float(os.environ.get(name) or default)
    except ValueError:
        return default
    return v if v > 0 else 0.0


def max_bytes():
    """The size cap in bytes (SPHEREX_FRAME_CACHE_MAX_GB), or 0 for unlimited."""
    return int(_env_float("SPHEREX_FRAME_CACHE_MAX_GB", DEFAULT_MAX_GB) * _GB)


def file_digest(path):
    """sha256 of a file's content. Remembered per (path, inode, size, mtime) for this process,
    so a file is read for hashing at most once until it changes (touching it re-hashes it)."""
    st = os.stat(path)
    sig = (str(path), st.st_ino, st.st_size, st.st_mtime_ns)
    with _lock:
        if sig in _digests:
            return _digests[sig]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    d = h.hexdigest()
    with _lock:
        if len(_digests) > 20000:
            _digests.clear()
        _digests[sig] = d
    return d


def _floats(a):
    return [float(x) for x in np.ravel(a)]       # json writes a float's shortest exact form


def grid_key(wcs, shape):
    """The grid as JSON-ready data, exact to the last bit of every number. Read from a
    normalised copy: WCSLIB fills in defaults (cunit '' -> 'deg', ...) the first time a WCS is
    used, so the caller's grid gives the same key before and after reprojecting with it."""
    w = wcs.deepcopy().wcs
    w.set()
    return {"shape": [int(n) for n in shape], "ctype": list(w.ctype), "cunit": [str(u) for u in w.cunit],
            "crval": _floats(w.crval), "crpix": _floats(w.crpix), "cdelt": _floats(w.cdelt),
            "pc": _floats(w.get_pc()), "lonpole": float(w.lonpole), "latpole": float(w.latpole),
            "radesys": str(w.radesys), "equinox": float(w.equinox) if np.isfinite(w.equinox) else None,
            "sip": wcs.sip is not None}


def _versions():
    import astropy
    import reproject
    import scipy
    return {"numpy": np.__version__, "scipy": scipy.__version__, "astropy": astropy.__version__,
            "reproject": reproject.__version__}


_VERSIONS = None


def frame_key(source, grid_wcs, shape, bad_flags, keep_saturated_stars, bloom_radius, wl_range):
    """Hex key of one aligned frame (see the module docstring for what it covers)."""
    global _VERSIONS
    if _VERSIONS is None:
        _VERSIONS = _versions()
    payload = {"v": FRAME_CACHE_VERSION, "lib": _VERSIONS, "source": file_digest(source),
               "bad_flags": sorted(str(b) for b in bad_flags), "keep_saturated_stars": bool(keep_saturated_stars),
               "bloom_radius": int(bloom_radius),
               "wl_range": None if wl_range is None else [float(wl_range[0]), float(wl_range[1])],
               "grid": grid_key(grid_wcs, shape)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def entry_path(key):
    return FRAME_DIR / key[:2] / f"{key}.npy"


def load(key, shape):
    """The stored frame: an array of `shape`, the string 'none' (frame never sees the
    wavelength range), or None (not stored, unreadable, or the wrong shape)."""
    path = entry_path(key)
    try:
        arr = np.load(path, allow_pickle=False)
    except Exception:                 # missing, evicted meanwhile, or damaged
        return None
    if arr.shape == (0,):
        out = "none"
    elif arr.shape == tuple(shape) and arr.dtype == np.float64:
        out = arr
    else:
        return None
    try:
        os.utime(path)                # most recently used: evicted last
    except OSError:
        pass
    return out


def save(key, layer):
    """Store a finished frame (array, or None for 'never sees the range') atomically."""
    global _writes
    path = entry_path(key)
    arr = np.empty(0) if layer is None else np.ascontiguousarray(layer, dtype=np.float64)
    part = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.part")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(part, "wb") as f:
            np.save(f, arr, allow_pickle=False)
        os.replace(part, path)
    except OSError:                   # full or read-only disk: only the speed-up is lost
        try:
            part.unlink()
        except OSError:
            pass
        return
    with _lock:
        _writes += 1
        due = _writes >= SWEEP_EVERY
    if due:
        sweep()


def has(source, grid_wcs, shape, bad_flags, keep_saturated_stars, bloom_radius, wl_range):
    """True when the cache is on and holds this frame's result (no reading of the entry)."""
    if not enabled():
        return False
    try:
        key = frame_key(source, grid_wcs, shape, bad_flags, keep_saturated_stars, bloom_radius, wl_range)
    except OSError:
        return False
    return entry_path(key).is_file()


def cached_layer(source, grid_wcs, shape, compute, bad_flags, keep_saturated_stars, bloom_radius, wl_range):
    """compute() -> aligned frame (array or None), through the cache when it is on."""
    if not enabled():
        return compute()
    try:
        key = frame_key(source, grid_wcs, shape, bad_flags, keep_saturated_stars, bloom_radius, wl_range)
    except OSError:                   # cannot read the source to hash it: let compute() report it
        return compute()
    hit = load(key, shape)
    if hit is not None:
        return None if isinstance(hit, str) else hit
    layer = compute()                 # an exception here stores nothing
    save(key, layer)
    return layer


def _entries():
    """[(mtime, size, path)] of every stored frame, oldest first."""
    out = []
    if not FRAME_DIR.is_dir():
        return out
    for p in FRAME_DIR.glob("*/*.npy"):
        try:
            st = p.stat()
        except OSError:
            continue
        out.append((st.st_mtime, st.st_size, p))
    out.sort(key=lambda e: e[0])
    return out


def sweep(force=False):
    """Delete least recently used entries until under the cap, and expired ones (TTL).
    Without force, does nothing unless entries were written since the last sweep.
    -> (entries removed, bytes removed)."""
    global _writes
    with _lock:
        if not force and _writes == 0:
            return 0, 0
        _writes = 0
    limit = max_bytes()
    ttl = _env_float("SPHEREX_CACHE_TTL_DAYS", 0.0)
    if not limit and not ttl:
        return 0, 0
    cutoff = time.time() - ttl * 86400 if ttl else None
    entries = _entries()
    total = sum(e[1] for e in entries)
    n = freed = 0
    for mtime, size, p in entries:
        expired = cutoff is not None and mtime < cutoff
        if not expired and not (limit and total > limit):
            continue
        try:
            p.unlink()
        except OSError:
            continue
        total -= size
        n += 1
        freed += size
    return n, freed


def info():
    """-> dict(entries, size_bytes, max_bytes, enabled, folder)."""
    entries = _entries()
    return {"entries": len(entries), "size_bytes": sum(e[1] for e in entries), "max_bytes": max_bytes(),
            "enabled": enabled(), "folder": FRAME_DIR}


def clear():
    """Delete the whole frame cache (never the downloaded cutouts) -> (entries, bytes) removed."""
    i = info()
    shutil.rmtree(FRAME_DIR, ignore_errors=True)
    with _lock:
        _digests.clear()
    return i["entries"], i["size_bytes"]
