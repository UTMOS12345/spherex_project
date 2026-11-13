"""Lesson 6 exercise solutions: check epochs, one frame vs stack, track the star.

    python lesson6_exercises.py "Barnard's Star" --detector D2
    python lesson6_exercises.py "WISE 0855" --detector D6
    python lesson6_exercises.py "R Draconis" --detector D3
"""
import argparse

import numpy as np
import astropy.units as u
from astropy.time import Time

from spherex import (parse_detectors, parse_target, at_time, load_or_find_frames, assign_epochs,
                     make_epochs, stack_epoch, get_cutout)


def sky_noise(img):
    """Robust noise of an image: spread of the typical pixels, ignoring stars and NaN."""
    return 1.4826 * np.nanmedian(np.abs(img - np.nanmedian(img)))


def find_star(ep, target, search_px=5):
    """Flux-weighted centroid within search_px grid pixels of the predicted position
    -> (sky position, peak value, predicted position).
    A centroid (centre of light) works even when the star's core is a flat, filled plateau,
    where "brightest pixel" would pick a random point on the plateau."""
    im, wcs = ep["image"], ep["wcs"]
    pred = at_time(target, Time(ep["mjd"], format="mjd"))
    px, py = wcs.world_to_pixel(pred)
    px, py = int(round(float(px))), int(round(float(py)))
    y0, x0 = max(py - search_px, 0), max(px - search_px, 0)
    box = im[y0: py + search_px + 1, x0: px + search_px + 1]
    if np.all(np.isnan(box)):
        return None, np.nan, pred
    w = np.clip(np.nan_to_num(box - np.nanmedian(im)), 0, None)   # only light above the sky
    w[w < 0.3 * w.max()] = 0                                         # ignore faint wings and neighbours
    yy, xx = np.mgrid[y0: y0 + box.shape[0], x0: x0 + box.shape[1]]
    cx, cy = (w * xx).sum() / w.sum(), (w * yy).sum() / w.sum()
    return wcs.pixel_to_world(cx, cy), np.nanmax(box), pred

p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--detector", default="D2")
p.add_argument("--size", type=float, default=0.1)
a = p.parse_args()

target = parse_target(a.target)
frames = assign_epochs(load_or_find_frames(a.target, target))

# ---------------------------------------------------------------- exercise 1
print("== 1) epochs ==")
gaps = np.diff(np.sort(np.asarray(frames["mjd"])))
print(f"{len(frames)} frames, {frames['epoch'].max() + 1} epochs, "
      f"{(gaps > 30).sum()} gaps longer than 30 days")
for e in sorted(set(frames["epoch"])):
    rows = frames[frames["epoch"] == e]
    span = rows["mjd"].max() - rows["mjd"].min()
    print(f"  epoch {e}: {rows['date'][0][:10]} -> {rows['date'][-1][:10]}  "
          f"({span:.1f} days, {len(rows)} frames, {np.isin(rows['detector'], parse_detectors(a.detector)).sum()} in {a.detector})")

epochs = make_epochs(frames, target, a.detector, size_deg=a.size)
if not epochs:
    raise SystemExit(f"No {a.detector} frames could be loaded. Run lesson4_cache.py first or try another detector.")

# ---------------------------------------------------------------- exercise 2
print("\n== 2) one frame vs the stack (epoch 0) ==")
ep0 = epochs[0]
row = frames[(frames["epoch"] == ep0["epoch"]) & np.isin(frames["detector"], parse_detectors(a.detector))][0]
one_path = get_cutout(row["access_url"], at_time(target, Time(row["mjd"], format="mjd")), a.size)
one, _ = stack_epoch([one_path], ep0["wcs"], ep0["image"].shape)
n1, ns = sky_noise(one), sky_noise(ep0["image"])
print(f"  single frame : empty {np.isnan(one).mean() * 100:5.1f}%   noise {n1:.4f} MJy/sr")
print(f"  stack ({ep0['n_frames']:2d})   : empty {np.isnan(ep0['image']).mean() * 100:5.1f}%   noise {ns:.4f} MJy/sr")
print(f"  noise is {n1 / ns:.1f}x lower (pure averaging would give sqrt({ep0['n_frames']}) = {np.sqrt(ep0['n_frames']):.1f}x)")

# ---------------------------------------------------------------- exercise 3
print("\n== 3) tracking the target ==")
print("  epoch  date         peak     moved since ep0   predicted   measured-vs-predicted")
first = first_pred = None
for ep in epochs:
    found, peak, pred = find_star(ep, target)
    if found is None:
        print(f"  {ep['epoch']}      {ep['date']}   no data near the predicted position")
        continue
    first = first or found
    first_pred = first_pred or pred
    moved = first.separation(found).to(u.arcsec)
    pmove = first_pred.separation(pred).to(u.arcsec)
    off = found.separation(pred).to(u.arcsec)
    print(f"  {ep['epoch']}      {ep['date']}   {peak:7.2f}  {moved:6.1f}          {pmove:6.1f}      {off:5.1f}")
print("  (measured positions are to the nearest grid pixel = 3\", so a few arcsec of scatter is normal)")
