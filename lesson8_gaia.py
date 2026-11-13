"""Lesson 8: Gaia DR3 stars on the SPHEREx image, with proper-motion arrows.

    python lesson8_gaia.py "Barnard's Star" --detector D2
    python lesson8_gaia.py "WISE 0855" --detector D6 --wise     # also CatWISE2020 (WISE) sources
"""
import argparse
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from spherex import (parse_target, at_time, load_or_find_frames, make_epochs,
                     gaia_overlay, draw_gaia, wise_overlay, shared_norm)

p = argparse.ArgumentParser()
p.add_argument("target")
p.add_argument("--detector", default="D2")
p.add_argument("--radius", type=float, default=0.08, help="Gaia search radius in degrees")
p.add_argument("--min-pm", type=float, default=50, help="arrows for stars faster than this (mas/yr)")
p.add_argument("--wise", action="store_true", help="also draw CatWISE2020 (WISE) sources")
p.add_argument("--years", type=float, default=5, help="arrow = motion over this many years")
a = p.parse_args()

target = parse_target(a.target)
epochs = make_epochs(load_or_find_frames(a.target, target), target, a.detector)
ep = epochs[-1]                                        # the latest epoch
t = Time(ep["mjd"], format="mjd")
center = ep["wcs"].pixel_to_world(ep["image"].shape[1] / 2, ep["image"].shape[0] / 2)

# ---- Gaia stars, moved to this epoch's date ----
stars = gaia_overlay(center, a.radius, t)
stars.sort("pm_total", reverse=True)
print(f"{len(stars)} Gaia DR3 stars within {a.radius} deg; positions moved to {ep['date']}")
print("fastest five:")
stars["source_id", "phot_g_mean_mag", "pmra", "pmdec", "pm_total"][:5].pprint(max_width=200)

# ---- picture ----
fig = plt.figure(figsize=(6.5, 6.5))
ax = fig.add_subplot(projection=ep["wcs"])
ax.imshow(ep["image"], origin="lower", cmap="gray", norm=shared_norm([ep["image"]]))
n_on = draw_gaia(ax, stars, ep["wcs"], ep["image"].shape, min_pm=a.min_pm, arrow_years=a.years)
wise = None
if a.wise:
    wise = wise_overlay(center, a.radius, t)
    n_w = draw_gaia(ax, wise, ep["wcs"], ep["image"].shape, min_pm=a.min_pm, arrow_years=a.years,
                    color="#e87ba4", fast_color="#eb6834", marker="s")
    print(f"{len(wise)} CatWISE2020 sources, {n_w} on the image (squares; orange = fast)")
ax.set_title(f"{a.target}  {a.detector}  {ep['date']}\ncyan circle = Gaia, "
             + ("pink square = WISE, " if a.wise else "")
             + f"yellow/orange = faster than {a.min_pm:g} mas/yr, "
             f"arrow = next {a.years:g} years", fontsize=9)
ax.set_xlabel("RA"); ax.set_ylabel("Dec")
Path("out").mkdir(exist_ok=True)
png = f"out/{re.sub(r'[^A-Za-z0-9]+', '_', a.target).strip('_')}_{a.detector}_gaia.png"
fig.savefig(png, dpi=120, bbox_inches="tight")
print(f"{n_on} Gaia stars on the image; saved {png}")

# ---- EXERCISE 1: is the target itself in Gaia? ----
now = at_time(target, t)                                            # where we expect the target (Lesson 2)
gaia_pos = SkyCoord(stars["ra_t"] * u.deg, stars["dec_t"] * u.deg)  # every Gaia star, at the same date
sep = gaia_pos.separation(now).to(u.arcsec)                         # distance of each star from the target
i = int(np.argmin(sep))                                             # row of the nearest one
print(f"\n1) nearest Gaia star to the target: {sep[i]:.2f} away")
print(f"   source_id {stars['source_id'][i]},  G = {stars['phot_g_mean_mag'][i]:.1f} mag,  "
      f"proper motion {stars['pm_total'][i]:.0f} mas/yr")
if sep[i] < 3 * u.arcsec:
    print("   -> the target IS a Gaia star (a known object)")
else:
    print("   -> no Gaia star at the target position (too faint or too cold for Gaia)")
if wise is not None and len(wise):
    wsep = SkyCoord(wise["ra_t"] * u.deg, wise["dec_t"] * u.deg).separation(now).to(u.arcsec)
    j = int(np.argmin(wsep))
    print(f"   nearest CatWISE2020 source: {wise['source_name'][j]}  {wsep[j]:.2f} away, "
          f"W2 = {wise['w2mpro'][j]:.1f} mag, motion {wise['pm_total'][j]:.0f} mas/yr")
    print("   -> " + ("WISE sees it" if wsep[j] < 3 * u.arcsec else "no WISE source there either"))

# ---- EXERCISE 2: how many fast stars? ----
fast = stars[stars["pm_total"] >= a.min_pm]
print(f"\n2) {len(fast)} of {len(stars)} Gaia stars move faster than {a.min_pm:g} mas/yr")
for row in fast:
    shift = row["pm_total"] / 1000 * (t.jyear - 2016.0)             # arcsec moved since Gaia's 2016 position
    print(f"   {row['source_id']}  {row['pm_total']:8.0f} mas/yr  moved {shift:6.1f}\" since 2016")

# ---- EXERCISE 3 ----
print('\n3) now run:  python lesson8_gaia.py "WISE 0855" --detector D6   and read answer 1 again')
