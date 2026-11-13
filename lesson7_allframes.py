"""Flipbook from EVERY frame of one detector (not just one picture per epoch).

    python lesson7_allframes.py "Barnard's Star" --detector D2
    python lesson7_allframes.py "Barnard's Star" --detector D2 --group 4   # average every 4 frames
"""
import argparse
import re
from pathlib import Path

import numpy as np
from astropy.time import Time

from spherex import (parse_detectors, parse_target, at_time, load_or_find_frames, assign_epochs, make_grid,
                     stack_epoch, get_cutout, make_gif)

p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--detector", default="D2")
p.add_argument("--group", type=int, default=1, help="average this many consecutive frames per picture")
p.add_argument("--size", type=float, default=0.1)
a = p.parse_args()

target = parse_target(a.target)
frames = assign_epochs(load_or_find_frames(a.target, target))
rows = frames[np.isin(frames["detector"], parse_detectors(a.detector))]

# the same fixed grid for every picture (as in make_epochs)
t_mid = Time((frames["mjd"].min() + frames["mjd"].max()) / 2, format="mjd")
grid_wcs, shape = make_grid(at_time(target, t_mid))

images, titles, markers = [], [], []
for e in sorted(set(rows["epoch"])):                       # never mix frames of different epochs
    ep_rows = rows[rows["epoch"] == e]
    for i in range(0, len(ep_rows), a.group):
        chunk = ep_rows[i: i + a.group]
        paths = []
        for row in chunk:
            try:
                paths.append(get_cutout(row["access_url"], at_time(target, Time(row["mjd"], format="mjd")), a.size))
            except OSError:
                pass
        if not paths:
            continue
        img, _ = stack_epoch(paths, grid_wcs, shape)       # 1 frame, or a small average
        mjd = float(np.mean(chunk["mjd"]))
        images.append(img)
        titles.append(f"{a.target} {a.detector}  {Time(mjd, format='mjd').iso[:10]}  (epoch {e}, {len(paths)} frame{'s' * (len(paths) > 1)})")
        markers.append(tuple(float(v) for v in grid_wcs.world_to_pixel(at_time(target, Time(mjd, format="mjd")))))

Path("out").mkdir(exist_ok=True)
safe = re.sub(r"[^A-Za-z0-9]+", "_", a.target).strip("_")
out = make_gif(images, titles, f"out/{safe}_{a.detector}_all_g{a.group}.gif", fps=4, markers=markers)
print(f"{len(images)} pictures -> {out}")
