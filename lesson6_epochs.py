"""Lesson 6 in pictures: what stacking does, and the target across epochs.

    python lesson6_show.py "Barnard's Star" --detector D2

Saves two PNGs in out/:
  ..._steps.png   row of 4: one raw frame | same frame cleaned | same frame on the grid | the stack
  ..._epochs.png  one panel per epoch, same grid and same stretch, green = predicted position
"""
import argparse
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astropy.time import Time
from astropy.visualization import ZScaleInterval, AsinhStretch, ImageNormalize

from spherex import (parse_target, at_time, load_or_find_frames, assign_epochs, make_epochs,
                     stack_epoch, get_cutout, clean_frame)


def norm_for(img):
    vmin, vmax = ZScaleInterval().get_limits(img[np.isfinite(img)])
    return ImageNormalize(vmin=vmin, vmax=vmax, stretch=AsinhStretch())


p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--detector", default="D2")
p.add_argument("--size", type=float, default=0.1)
a = p.parse_args()

target = parse_target(a.target)
frames = assign_epochs(load_or_find_frames(a.target, target))
epochs = make_epochs(frames, target, a.detector, size_deg=a.size)
if not epochs:
    raise SystemExit(f"No {a.detector} frames available.")
Path("out").mkdir(exist_ok=True)
safe = re.sub(r"[^A-Za-z0-9]+", "_", a.target).strip("_") + "_" + a.detector
cmap = plt.get_cmap("gray").copy()
cmap.set_bad("red")                                   # missing pixels show in red

# ---------- picture 1: the steps, for the first frame of the first epoch ----------
ep = epochs[0]
row = frames[(frames["epoch"] == ep["epoch"]) & (frames["detector"] == a.detector)][0]
path = get_cutout(row["access_url"], at_time(target, Time(row["mjd"], format="mjd")), a.size)
f = clean_frame(path)
one, _ = stack_epoch([path], ep["wcs"], ep["image"].shape, keep_saturated_stars=False)
panels = [(f["raw"], "1. one raw frame\n(rotated, with sky glow)"),
          (f["image"], "2. cleaned (Lesson 5)\nred = masked pixels"),
          (one, "3. same frame on the common grid\n(north up)"),
          (ep["image"], f"4. stack of {ep['n_frames']} frames\n(holes filled, less noise)")]
fig, axes = plt.subplots(1, 4, figsize=(17, 4.6))
for ax, (img, title) in zip(axes, panels):
    ax.imshow(img, origin="lower", cmap=cmap, norm=norm_for(img))
    ax.set_title(title, fontsize=10)
    ax.set_xticks([]); ax.set_yticks([])
fig.suptitle(f"{a.target}  {a.detector}  epoch {ep['epoch']} ({ep['date']})")
fig.savefig(f"out/{safe}_steps.png", dpi=110, bbox_inches="tight")
plt.close(fig)
print(f"saved out/{safe}_steps.png")

# ---------- picture 2: every epoch, same grid, same stretch ----------
norm = norm_for(epochs[-1]["image"])
fig = plt.figure(figsize=(4.6 * len(epochs), 4.9))
for i, ep in enumerate(epochs):
    ax = fig.add_subplot(1, len(epochs), i + 1, projection=ep["wcs"])
    ax.imshow(ep["image"], origin="lower", cmap=cmap, norm=norm)
    x, y = ep["wcs"].world_to_pixel(at_time(target, Time(ep["mjd"], format="mjd")))
    ax.scatter([x], [y], s=350, facecolors="none", edgecolors="lime", lw=1.2)
    x0, y0 = ep["wcs"].world_to_pixel(at_time(target, Time(epochs[0]["mjd"], format="mjd")))
    ax.plot([x0], [y0], "+", color="orange", ms=12)   # where it was in the first epoch
    ax.set_title(f"epoch {ep['epoch']}  {ep['date']}  ({ep['n_frames']} frames)", fontsize=10)
    ax.set_xlabel("RA"); ax.set_ylabel("Dec" if i == 0 else " ")
fig.suptitle(f"{a.target}  {a.detector}: green circle = predicted position, orange + = position in the first epoch")
fig.savefig(f"out/{safe}_epochs.png", dpi=110, bbox_inches="tight")
plt.close(fig)
print(f"saved out/{safe}_epochs.png")
