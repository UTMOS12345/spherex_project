"""Why is the star missing from some stacks? Check every frame of one epoch.

    python lesson6_diagnose.py "Barnard's Star" --detector D2 --epoch 0
"""
import argparse

import numpy as np
import astropy.units as u
from astropy.time import Time

from spherex import (parse_detectors, parse_target, at_time, load_or_find_frames, assign_epochs, make_epochs,
                     get_cutout, clean_frame, decode_flags)


def peak_near(img, x, y, r=2):
    """Max value and its offset (pixels) within r pixels of (x, y)."""
    xi, yi = int(round(float(x))), int(round(float(y)))
    box = img[max(yi - r, 0): yi + r + 1, max(xi - r, 0): xi + r + 1]
    if box.size == 0 or np.all(np.isnan(box)):
        return np.nan
    return np.nanmax(box)


p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--detector", default="D2")
p.add_argument("--epoch", type=int, default=0)
p.add_argument("--size", type=float, default=0.1)
a = p.parse_args()

target = parse_target(a.target)
frames = assign_epochs(load_or_find_frames(a.target, target))
rows = frames[(frames["epoch"] == a.epoch) & np.isin(frames["detector"], parse_detectors(a.detector))]

# ---- A: frame by frame, is the star there, and is its core masked? ----
print(f"== A) every {a.detector} frame of epoch {a.epoch} ==")
print(" date        raw peak   cleaned peak  centre NaN?  flags at the star")
n_hole = 0
for row in rows:
    t = Time(row["mjd"], format="mjd")
    pos = at_time(target, t)
    f = clean_frame(get_cutout(row["access_url"], pos, a.size))
    x, y = f["wcs"].world_to_pixel(pos)
    xi, yi = int(round(float(x))), int(round(float(y)))
    hole = bool(np.isnan(f["image"][yi, xi]))
    n_hole += hole
    flags = [n.removeprefix("MP_") for n in decode_flags(f["flags"][yi, xi], f["bits"])]
    print(f" {row['date'][:10]}  {peak_near(f['raw'], x, y):9.1f}   {peak_near(f['image'], x, y):9.1f}"
          f"     {'YES' if hole else 'no ':3s}       {', '.join(flags) or '-'}")
print(f"-> the star's centre is masked in {n_hole} of {len(rows)} frames")

# ---- B: stack with the normal mask vs keeping saturated star pixels ----
print("\n== B) stack: normal mask vs keep_saturated_stars ==")
for label, keep in [("normal mask    ", False), ("keep saturated ", True)]:
    ep = make_epochs(frames[frames["epoch"] == a.epoch], target, a.detector,
                     size_deg=a.size, keep_saturated_stars=keep)[0]
    pred = at_time(target, Time(ep["mjd"], format="mjd"))
    x, y = ep["wcs"].world_to_pixel(pred)
    xi, yi = int(round(float(x))), int(round(float(y)))
    print(f"  {label}: value at predicted position {ep['image'][yi, xi]:9.2f}   "
          f"peak within 6\" {peak_near(ep['image'], x, y, r=2):9.2f}   "
          f"empty {np.isnan(ep['image']).mean() * 100:.1f}%")
