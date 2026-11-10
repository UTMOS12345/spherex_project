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
    """Download to a temp file, verify it, then move it into the cache."""
    tmp = download_file(url, cache=False, timeout=120, show_progress=False)
    try:
        if not is_valid_fits(tmp):
            raise OSError("downloaded file is not valid FITS")
        shutil.move(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dest


def get_cutout(url, center, size_deg=0.1, tries=6):
    """Frame URL + SkyCoord centre -> local path of the cutout (downloads only if not cached)."""
    path = cache_path(url, center, size_deg)
    if path.exists() and is_valid_fits(path):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    return with_retries(_download_checked, cutout_url(url, center, size_deg), path, tries=tries)


def prefetch(frames, target, size_deg=0.1, limit=None):
    """Download cutouts for many frames, centred on the target's position on each date.
    Safe to stop and re-run: cached files are skipped. Returns (cached, downloaded, failed)."""
    hit = new = fail = 0
    rows = frames if limit is None else frames[:limit]
    for i, row in enumerate(rows):
        center = at_time(target, Time(row["mjd"], format="mjd"))
        cached = cache_path(row["access_url"], center, size_deg).exists()
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
