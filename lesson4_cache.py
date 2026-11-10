"""Lesson 4: download cutouts into the disk cache (resumable).

    python lesson4_cache.py "Barnard's Star" --limit 12
"""
import argparse
import time

import numpy as np

from spherex import parse_target, load_or_find_frames, prefetch, check_cache, load_image, CACHE_DIR

p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--limit", type=int, default=None)
p.add_argument("--size", type=float, default=0.1)
p.add_argument("--refresh", action="store_true", help="search IRSA again instead of the saved table")
a = p.parse_args()

target = parse_target(a.target)
frames = load_or_find_frames(a.target, target, refresh=a.refresh)
print(f"{len(frames)} frames")

t0 = time.time()
prefetch(frames, target, a.size, a.limit)
print(f"took {time.time() - t0:.1f} s")

# ---- EXERCISE 3: is every cached file a complete, valid FITS file? ----
n_valid, bad = check_cache()
print(f"\ncache check: {n_valid} valid, {len(bad)} bad")
for b in bad:
    print("  BAD:", b.name)

# ---- EXERCISE 5: is the star really at the centre of each cutout? ----
print("\ncentring check (detectors D1-D3):")
for path in sorted(CACHE_DIR.glob("*.fits")):
    if path in bad:
        continue                                  # can't open a broken file
    img, wcs, hdr = load_image(path)
    det = int(hdr["DETECTOR"])                    # 1..6, written in the IMAGE header
    if det > 3:
        continue                                  # only the short-wavelength detectors
    ny, nx = img.shape
    box = img[ny // 2 - 3: ny // 2 + 4, nx // 2 - 3: nx // 2 + 4]   # central 7x7 pixels, [y, x]
    ratio = np.nanmax(box) / np.nanmedian(img)
    print(f"  D{det}  centre peak {np.nanmax(box):9.1f}  median {np.nanmedian(img):6.3f}  "
          f"ratio {ratio:8.0f}  {'OK' if ratio > 100 else 'CHECK'}  {path.name[:40]}")
