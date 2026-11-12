"""Lesson 10: spectrum = the target's brightness at every wavelength, during one visit.

    python lesson10_spectrum.py "WISE 0855" --epoch 0 --dark
    python lesson10_spectrum.py "RW Aur" --epoch -1 --log
"""
import argparse
import re
import warnings
from pathlib import Path

import numpy as np

warnings.simplefilter("ignore", RuntimeWarning)
from spherex import (parse_target, load_or_find_frames, epoch_frames, spectrum, bin_to_channels,
                     plot_spectrum, set_style)

p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--epoch", type=int, default=0, help="which visit: 0 = first, -1 = latest")
p.add_argument("--radius", type=float, default=2.0, help="aperture radius in pixels")
p.add_argument("--log", action="store_true", help="logarithmic brightness axis")
p.add_argument("--dark", action="store_true")
a = p.parse_args()

target = parse_target(a.target)
frames = epoch_frames(load_or_find_frames(a.target, target), a.epoch)
print(f"visit {a.epoch}: {len(frames)} frames, {frames['date'][0][:10]} to {frames['date'][-1][:10]}")
print("frames per detector:", {d: int((frames["detector"] == d).sum()) for d in sorted(set(frames["detector"]))})

spec = spectrum(frames, target, r_px=a.radius)
binned = bin_to_channels(spec)
good = spec[spec["ok"]]
print(f"\n{len(spec)} measurements, {len(good)} usable, {int(spec['saturated'].sum())} saturated; "
      f"{len(binned)} of 102 channels have usable data")
binned.pprint(max_lines=30, max_width=200)

set_style(dark=a.dark)
Path("out").mkdir(exist_ok=True)
png = f"out/{re.sub(r'[^A-Za-z0-9]+', '_', a.target).strip('_')}_spectrum_visit{a.epoch}.png"
plot_spectrum(spec, binned, f"{a.target}: spectrum, visit of {frames['date'][0][:10]}", png, log=a.log)
print("saved", png)

# ======================================================================================
# EXERCISES (try them yourself first - the solutions follow)
#   1. Per detector: how many usable points, and how many were rejected?
#   2. At which wavelength is the target brightest?
#   3. Colour: brightness at ~4.5 um divided by brightness at ~1.5 um.
#      A normal star is FAINTER at 4.5 than at 1.5 (ratio < 1); a very cold object like
#      WISE 0855 is the opposite (ratio >> 1).
# ======================================================================================

# ---- solution 1 ----
print("\n1) per detector:")
for d in range(1, 7):
    sel = spec[spec["detector"] == d]
    print(f"   D{d}: {int(sel['ok'].sum()):3d} usable, {int((~sel['ok']).sum()):3d} rejected")


# ---- solution 2 ----
def flux_near(wl, half_width=0.1):
    """Mean usable flux within half_width micron of wl (NaN if none)."""
    sel = good[np.abs(good["wavelength_um"] - wl) <= half_width]
    return float(np.mean(sel["flux_mjy"])) if len(sel) else np.nan


if len(binned):
    i = int(np.argmax(binned["flux_mjy"]))
    print(f"\n2) brightest channel: {binned['wavelength_um'][i]:.2f} um "
          f"(D{binned['detector'][i]}), {binned['flux_mjy'][i]:.3f} mJy")

# ---- solution 3 ----
f15, f45 = flux_near(1.5), flux_near(4.5)
print(f"\n3) flux at 1.5 um: {f15:.3f} mJy   at 4.5 um: {f45:.3f} mJy")
if np.isfinite(f15) and np.isfinite(f45) and f15 > 0:
    print(f"   ratio 4.5/1.5 = {f45 / f15:.1f}  ->  "
          f"{'much brighter at long wavelengths: a very cold object' if f45 / f15 > 3 else 'normal star colours'}")
elif np.isfinite(f45) and not (np.isfinite(f15) and f15 > 0):
    print("   seen at 4.5 um but not at 1.5 um: invisible at short wavelengths, like a very cold brown dwarf")
else:
    print("   not enough usable data at one of the two wavelengths")
