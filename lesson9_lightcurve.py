"""Lesson 9: light curve = brightness of the target over time, at one wavelength.

    python lesson9_lightcurve.py "RW Aur" --band 1.6
    python lesson9_lightcurve.py "R Draconis" --band 2.2 --tol 0.1
"""
import argparse
import warnings
import re
from pathlib import Path

import numpy as np
from astropy.time import Time

warnings.simplefilter("ignore", RuntimeWarning)    # "mean of empty slice" when a sky ring is fully masked
from spherex import parse_target, load_or_find_frames, light_curve, plot_light_curve, plot_light_curve_simple, set_style

p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--band", type=float, default=1.6, help="wavelength in micron")
p.add_argument("--tol", type=float, default=0.05, help="accept frames within this many micron of --band")
p.add_argument("--panels", action="store_true", help="one panel per visit instead of the simple plot")
p.add_argument("--dark", action="store_true", help="dark theme for the plot")
p.add_argument("--radius", type=float, default=2.0, help="aperture radius in pixels")
a = p.parse_args()

target = parse_target(a.target)
frames = load_or_find_frames(a.target, target)
lc = light_curve(frames, target, a.band, tol_um=a.tol, r_px=a.radius)
if len(lc) == 0:
    raise SystemExit("No frame has the target at that wavelength. Try a bigger --tol.")

lc["date", "wavelength_um", "flux_mjy", "err_mjy", "n_bad", "bad_flags", "ok"].pprint(
    max_lines=40, max_width=200)
good = lc[lc["ok"]]
print(f"\n{len(lc)} measurements, {len(good)} usable, {int(lc['saturated'].sum())} saturated")
if len(good) > 1:
    print(f"usable flux: median {np.median(good['flux_mjy']):.1f} mJy, "
          f"from {good['flux_mjy'].min():.1f} to {good['flux_mjy'].max():.1f} mJy")

# ---- picture: one panel per visit ----
Path("out").mkdir(exist_ok=True)
png = f"out/{re.sub(r'[^A-Za-z0-9]+', '_', a.target).strip('_')}_lightcurve_{a.band:g}um.png"
set_style(dark=a.dark)
(plot_light_curve if a.panels else plot_light_curve_simple)(lc, f"{a.target}: brightness at {a.band:g} ± {a.tol:g} µm", png)
print("saved", png)

# ---- EXERCISE 1: average the usable points of each visit ----
print("\n1) per visit (usable points only):")
visits = []
if len(good):
    visit_id = np.concatenate([[0], np.cumsum(np.diff(good["mjd"]) > 30)])   # new visit after a 30-day gap
    for v in sorted(set(visit_id)):
        rows = good[visit_id == v]
        mean = float(np.mean(rows["flux_mjy"]))
        scatter = float(np.std(rows["flux_mjy"])) if len(rows) > 1 else np.nan
        visits.append((mean, scatter, len(rows)))
        pct = f"{scatter / mean * 100:4.1f}%" if len(rows) > 1 else "  - "
        print(f"   visit {v}: {rows['date'][0][:10]}  {len(rows):2d} points  mean {mean:9.2f} mJy  "
              f"scatter inside the visit {pct}")
else:
    print("   no usable points")

# ---- EXERCISE 2: is the change between visits real? ----
print("\n2) did the brightness change between visits?")
means = np.array([m for m, s_, n in visits])
scatters = np.array([s_ for m, s_, n in visits if np.isfinite(s_)])
if len(means) < 2:
    print("   need usable points in at least 2 visits")
elif len(scatters) == 0:
    print("   only one point per visit: can't measure the scatter. Try a bigger --tol.")
else:
    change = means.max() - means.min()                       # biggest difference between visit means
    typical = float(np.median(scatters))                     # typical scatter inside one visit
    ratio = change / typical if typical > 0 else np.inf
    print(f"   biggest change between visits: {change:.2f} mJy ({change / means.mean() * 100:.1f}% of the mean)")
    print(f"   typical scatter inside a visit: {typical:.2f} mJy")
    if ratio > 5:
        verdict = "a clear change: much bigger than the scatter"
    elif ratio > 3:
        verdict = "a probable change"
    else:
        verdict = "no change that stands out from the scatter"
    print(f"   change / scatter = {ratio:.1f}  ->  {verdict}")

# ---- EXERCISE 3: saturation in the numbers ----
n_sat = int(lc["saturated"].sum())
print(f"\n3) saturated measurements: {n_sat} of {len(lc)}")
if n_sat == len(lc):
    print("   every frame is saturated: this target is too bright to measure at this wavelength")
elif n_sat:
    print("   some frames are saturated: they are excluded (grey crosses in the plot)")
