"""Lessons 1-4 together: type a target, get PNGs of the first N frames with the star marked
where it is on each frame's date (green) and its J2000 catalog position (red).

    python show_target.py "Barnard's Star" --n 3
"""
import argparse
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy.visualization import ZScaleInterval, AsinhStretch, ImageNormalize

from spherex import parse_target, at_time, has_pm, load_or_find_frames, get_cutout, load_image, sky_to_pix, inside

p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--n", type=int, default=1)
p.add_argument("--size", type=float, default=0.1)
a = p.parse_args()

coord = parse_target(a.target)
frames = load_or_find_frames(a.target, coord)
print(f"{len(frames)} frames")
out = Path("out"); out.mkdir(exist_ok=True)
safe = re.sub(r"[^A-Za-z0-9]+", "_", a.target).strip("_")

for i, row in enumerate(frames[: a.n]):
    now = at_time(coord, Time(row["mjd"], format="mjd"))
    try:
        path = get_cutout(row["access_url"], now, a.size)
    except OSError as e:
        print(f"[{i}] skipped: {e}")
        continue
    img, wcs, hdr = load_image(path)
    good = np.isfinite(img)
    vmin, vmax = ZScaleInterval().get_limits(img[good])
    ax = plt.figure(figsize=(6, 6)).add_subplot(projection=wcs)
    ax.imshow(img, origin="lower", cmap="gray", norm=ImageNormalize(vmin=vmin, vmax=vmax, stretch=AsinhStretch()))
    x, y = sky_to_pix(wcs, now)
    ax.scatter([x], [y], s=300, facecolors="none", edgecolors="lime", label="on this date")
    if has_pm(coord):
        x0, y0 = sky_to_pix(wcs, SkyCoord(coord.ra, coord.dec))
        if inside(img.shape, x0, y0):
            ax.scatter([x0], [y0], s=300, facecolors="none", edgecolors="red", label="J2000 catalog")
    ax.set_title(f"{a.target} | {row['date'][:16]} | {row['detector']} ({row['band_um']} um band)", fontsize=9)
    ax.legend(loc="upper right", fontsize=7)
    png = out / f"{safe}_{i:02d}.png"
    plt.savefig(png, dpi=120, bbox_inches="tight"); plt.close()
    print(f"[{i}] {row['date'][:10]} {row['detector']} -> {png}")
