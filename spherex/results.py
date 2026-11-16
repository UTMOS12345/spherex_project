"""Saved results: the expensive steps of a view, kept on disk so the next request loads them.

Saved under <cache>/results/<target>/<kind>_<key>.pkl (the target folder uses the same name
as its frame list, cache/frames/<target>.ecsv):
    stacks       the stacked visits behind the video, pictures and overlays (api._epochs)
    light_curve  the measured light-curve table (before drawing)
    spectrum     the measured spectrum of one visit (before binning and drawing)

The key is a hash of everything that changes the result: the target's position and motion,
the detector or wavelength range, field of view, time step, clip on/off,
keep_saturated_stars, the exact list of frames used (so a refresh that brings a new data
release or newer frames gives a new key), the spherex version and RESULTS_VERSION.
Figures are always drawn fresh from the loaded result, so they are the same as computing
everything again.

A result is saved only when every image it asked for was there: a view computed offline with
a partly downloaded target is not saved, so downloading the rest later is never hidden by an
old result. Files are written to a temporary name and renamed (atomic), and a file that
cannot be read is ignored (recomputed). The files are Python pickles written by this
library into the user's own cache; never load results from someone else's folder.
"""
import hashlib
import json
import os
import pickle
import re
import threading
from collections import OrderedDict
from pathlib import Path

from . import __version__
from .net import CACHE_ROOT

RESULTS_VERSION = 1       # raise when a change in the code changes any saved result
RESULTS_DIR = CACHE_ROOT / "results"
MEMORY_ITEMS = 48         # results kept in memory after loading (preload warms this)

_mem = OrderedDict()      # path -> object
_lock = threading.Lock()


def safe_name(name):
    """The file-name form of a target name (the rule of frames.table_path)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "target"


def target_dir(name):
    return RESULTS_DIR / safe_name(name)


def frames_key(frames):
    """One hash of the frames used, in order (their URLs name release, exposure and detector)."""
    return hashlib.sha256("\n".join(str(u) for u in frames["access_url"]).encode()).hexdigest()


def _coord(target):
    """Position and motion of a SkyCoord, rounded far below anything that changes a picture."""
    out = {"ra": round(float(target.ra.deg), 8), "dec": round(float(target.dec.deg), 8)}
    try:
        out["pm"] = [round(float(target.pm_ra_cosdec.value), 4), round(float(target.pm_dec.value), 4)]
        out["epoch"] = round(float(target.obstime.jyear), 4)
    except (AttributeError, TypeError):
        pass
    return out


def result_path(name, kind, target, **parts):
    """Path of the saved result of `kind` for target `name` (SkyCoord `target`) with these parts."""
    payload = dict(kind=kind, target=_coord(target), spherex=__version__, results=RESULTS_VERSION, **parts)
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]
    return target_dir(name) / f"{kind}_{key}.pkl"


def _remember(path, obj):
    with _lock:
        _mem[path] = obj
        _mem.move_to_end(path)
        while len(_mem) > MEMORY_ITEMS:
            _mem.popitem(last=False)


def load(path, touch=True):
    """The saved result at `path`, or None (not saved, or unreadable). touch: mark it as used
    (its modification time is what 'most recent' means for preloading)."""
    path = Path(path)
    with _lock:
        if path in _mem:
            _mem.move_to_end(path)
            return _mem[path]
    try:
        with open(path, "rb") as f:
            obj = pickle.load(f)
    except Exception:              # missing, half-written by a crash, or from an old version
        return None
    if touch:
        try:
            os.utime(path)
        except OSError:
            pass
    _remember(path, obj)
    return obj


def save(path, obj):
    """Write obj to path atomically (temporary file in the same folder, then rename)."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.part")
        with open(part, "wb") as f:
            pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(part, path)
    except OSError:                # a full or read-only disk only costs the speed-up
        try:
            part.unlink()
        except (OSError, UnboundLocalError):
            pass
        return
    _remember(path, obj)


def preload(paths):
    """Read saved results into memory (disk only, never computes or downloads). -> how many."""
    n = 0
    for p in paths:
        if load(p, touch=False) is not None:
            n += 1
    return n


def forget(name):
    """Drop a target's results from memory (after its files were removed)."""
    folder = target_dir(name)
    with _lock:
        for p in [p for p in _mem if Path(p).parent == folder]:
            del _mem[p]
