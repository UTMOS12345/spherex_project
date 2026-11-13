"""Lesson 4 - cutouts with retries and a disk cache that never holds broken files."""
import os
import shutil
from pathlib import Path

from astropy.io import fits
from astropy.time import Time
from astropy.utils.data import download_file

from .net import with_retries
from .targets import at_time

CACHE_DIR = Path("cache/cutouts")

# Every download is at least this big (degrees). Smaller views are then made from the same
# file, so changing the field of view later never needs a new download. 0.25 deg = 15'
# (a north-up view of up to ~10' fits inside, whatever the frame's rotation).
DOWNLOAD_DEG = 0.25

# Layers dropped before saving: the PSF cube is ~5 MB per file, ~95% of a cutout, and
# nothing in this project uses it. WCS-WAVE (the wavelength map) is kept.
DROP_LAYERS = ("PSF", "EPSF")


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
        return path
    fetch = max(size_deg, DOWNLOAD_DEG)
    path = cache_path(url, center, fetch)
    path.parent.mkdir(parents=True, exist_ok=True)
    return with_retries(_download_checked, cutout_url(url, center, fetch), path, tries=tries)


def prefetch(frames, target, size_deg=0.1, limit=None):
    """Download cutouts for many frames, centred on the target's position on each date.
    Safe to stop and re-run: cached files are skipped. Returns (cached, downloaded, failed)."""
    hit = new = fail = 0
    rows = frames if limit is None else frames[:limit]
    for i, row in enumerate(rows):
        center = at_time(target, Time(row["mjd"], format="mjd"))
        cached = find_cached(row["access_url"], center, size_deg) is not None
        try:
            get_cutout(row["access_url"], center, size_deg)
            hit += cached
            new += not cached
            print(f"[{i + 1}/{len(rows)}] {'cached' if cached else 'downloaded'}  {row['date'][:10]} {row['detector']}")
        except OSError as e:
            fail += 1
            print(f"[{i + 1}/{len(rows)}] FAILED {row['obs_id']} {row['detector']}: {e}")
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
