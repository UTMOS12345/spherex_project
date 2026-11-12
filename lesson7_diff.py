"""Lesson 7: flipbook GIF of the epochs + a difference image.

    python lesson7_diff.py "Barnard's Star" --detector D2

Saves in out/:  <target>_<det>_flipbook.gif   and   <target>_<det>_diff.png
"""
import argparse
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astropy.time import Time

from spherex import (parse_target, at_time, load_or_find_frames, make_epochs,
                     difference, make_gif, shared_norm)

p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--detector", default="D2")
p.add_argument("--size", type=float, default=0.1)
p.add_argument("--days", type=float, default=60, help="longest time span of one picture, in days")
p.add_argument("--fps", type=float, default=3)
a = p.parse_args()

target = parse_target(a.target)
frames = load_or_find_frames(a.target, target)
epochs = make_epochs(frames, target, a.detector, size_deg=a.size,
                     gap_days=min(30, a.days), max_len_days=a.days)
print(f"{len(epochs)} pictures, frames in each: {[ep['n_frames'] for ep in epochs]}")
if len(epochs) < 2:
    raise SystemExit("Need at least 2 epochs for a flipbook or a difference.")
Path("out").mkdir(exist_ok=True)
safe = re.sub(r"[^A-Za-z0-9]+", "_", a.target).strip("_") + "_" + a.detector

# ---- 1. flipbook: one picture per epoch, same grid, same brightness scale ----
images = [ep["image"] for ep in epochs]
titles = [f"{a.target}  {a.detector}  {ep['date']}  ({ep['n_frames']} frames)" for ep in epochs]
markers = [tuple(float(v) for v in ep["wcs"].world_to_pixel(at_time(target, Time(ep["mjd"], format="mjd"))))
           for ep in epochs]
gif = make_gif(images, titles, f"out/{safe}_flipbook.gif", fps=a.fps, markers=markers,
               mjds=[ep["mjd"] for ep in epochs])
print("saved", gif)

# ---- 2. difference: last epoch minus first epoch ----
first, last = epochs[0], epochs[-1]
d = difference(last, first)
print(f"difference: {d['label']}")

lim = np.nanpercentile(np.abs(d["image"]), 99.5)                  # symmetric colour limits
norm = shared_norm([first["image"], last["image"]])
fig = plt.figure(figsize=(14, 4.8))
for i, (img, title, kw) in enumerate([
        (first["image"], f"B: {first['date']}", dict(cmap="gray", norm=norm)),
        (last["image"], f"A: {last['date']}", dict(cmap="gray", norm=norm)),
        (d["image"], "A - B   (red = brighter in A, blue = brighter in B)",
         dict(cmap="RdBu_r", vmin=-lim, vmax=lim))]):
    ax = fig.add_subplot(1, 3, i + 1, projection=d["wcs"])
    ax.imshow(img, origin="lower", **kw)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("RA"); ax.set_ylabel("Dec" if i == 0 else " ")
fig.savefig(f"out/{safe}_diff.png", dpi=110, bbox_inches="tight")
print(f"saved out/{safe}_diff.png")

# ---- EXERCISE ----
# 1. find the brightest (+) and the most negative (-) pixel of d["image"], convert both to
#    RA/Dec with d["wcs"].pixel_to_world(x, y), print their separation in arcsec
# 2. compare with how far at_time() says the target moved between the two epochs
# 3. how well did everything else cancel? robust noise of d["image"] vs of last["image"]
