"""Blind-search validation: run api.find_movers on each target's field WITHOUT telling it where the
target is, then check where the target came out. Writes validate_search.json and thumbnails.

    python tools/validate_search.py out/validation                  # the five challenge targets
    python tools/validate_search.py out/validation "WISE 0855:D6"   # one field (target:detector)

Uses the images already downloaded (demo mode): run the app or prepare_demo.py first.
Per field and clip setting it records: whether a candidate lies within RECOVER_ARCSEC of the
target's position on that visit's date (rank, type, implied motion), every cut count, every
candidate (with its distance from the target), the candidates more than REST_ARCMIN from the
target (the rest of the field), the Gaia stars moving faster than 0.2"/yr in the field (so a real
second mover is not mistaken for a false positive), the runtime, and one thumbnail per candidate.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))   # repo root, so tools/ can import spherex
import json
import os
import time

import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from spherex import api, asteroids, net
from spherex.gaia import gaia_overlay
from spherex.targets import at_time

FIELDS = ["Barnard's Star:D2", "Epsilon Indi B:D5", "WISE 0855:D6", "RW Aur:D1", "R Draconis:D3"]
RECOVER_ARCSEC = 10.0     # a candidate this close to the target's predicted position is the target
REST_ARCMIN = 2.0         # candidates further than this from the target: the rest of the field
FAST_MAS_YR = 200         # Gaia stars moving faster than this are listed per field


def _memo_skybot():
    """Ask SkyBoT once per date and circle in this run (it is slow)."""
    memo, orig = {}, asteroids.known_asteroids

    def known(center, radius, t):
        key = (round(center.ra.deg, 6), round(center.dec.deg, 6), round(radius, 6), round(t.mjd, 6))
        if key not in memo:
            memo[key] = orig(center, radius, t)
        return memo[key]
    asteroids.known_asteroids = known


def run_field(name, det, clip, out_dir):
    target = api._parse(name)
    info = api.resolve(name)
    t0 = time.time()
    tab, eps = api.find_movers(name, fov=10.0, detector=det, clip=clip, asteroids=True, _with_epochs=True)
    seconds = time.time() - t0
    tag = f"{name.replace(' ', '_').replace(chr(39), '')}_{det}_{'clip' if clip else 'noclip'}"
    thumbs = api.search_thumbnails(tab, os.path.join(out_dir, "thumbs", tag), text=name, detector=det,
                                   fov=10.0, clip=clip)
    dates = {e["date"]: e["mjd"] for e in eps}
    rows = []
    for k, r in enumerate(tab):
        gone = r["type"] == "single" and r["sign"] < 0        # its position refers to the earlier visit
        here = at_time(target, Time(dates[str(r["date_a" if gone else "date_b"])], format="mjd"))
        sep = SkyCoord(r["ra"] * u.deg, r["dec"] * u.deg).separation(here).arcsec
        rows.append(dict(rank=int(r["rank"]), pair=str(r["pair"]), type=str(r["type"]),
                         peak_to_noise=round(float(r["peak_to_noise"]), 1), sign=int(r["sign"]),
                         pm=float(r["pm_arcsec_yr"]), pa=float(r["pm_pa_deg"]), change=float(r["change"]),
                         label=str(r["label"]), nearest=str(r["nearest_match"]),
                         nearest_sep=float(r["nearest_sep_arcsec"]), gaia_g=float(r["gaia_g"]),
                         gaia_pm=float(r["gaia_pm_arcsec_yr"]), saturated=bool(r["saturated"]),
                         release_boundary=bool(r["release_boundary"]), seen=f"{r['seen_in']}/{r['seen_possible']}",
                         sep_target=float(sep), thumb=os.path.relpath(thumbs[k], out_dir)))
    shape = eps[0]["image"].shape
    center = eps[0]["wcs"].pixel_to_world(shape[1] / 2, shape[0] / 2)
    try:
        g = gaia_overlay(center, 0.1, Time(eps[0]["mjd"], format="mjd"))
        fast = g[np.asarray(g["pm_total"], float) > FAST_MAS_YR]
        fast = [dict(source_id=str(s["source_id"]), pm=round(float(s["pm_total"]) / 1000, 3),
                     g=round(float(s["phot_g_mean_mag"]), 1)) for s in fast]
    except Exception as e:
        fast = [f"Gaia failed: {type(e).__name__}"]
    rest = [x for x in rows if x["sep_target"] > REST_ARCMIN * 60]
    return dict(tag=tag, target=name, detector=det, clip=clip, seconds=round(seconds, 1),
                catalogue_pm=float(np.hypot(info["pm_ra"], info["pm_dec"]) / 1000) if info.get("has_motion") else 0.0,
                dates=tab.meta["settings"]["dates"], releases=tab.meta["settings"]["releases"],
                frames=[int(e["n_frames"]) for e in eps], n_min=[int(e["n_min"]) for e in eps],
                cuts=tab.meta["cuts"], labels=tab.meta["catalogues"]["labels"],
                failed=tab.meta["catalogues"]["failed"], chance=tab.meta["catalogues"]["chance_match"],
                n=len(tab), found=[x for x in rows if x["sep_target"] <= RECOVER_ARCSEC],
                rest=len(rest), rest_unexplained=sum(x["label"] == "unexplained" for x in rest),
                gaia_fast_movers=fast, rows=rows)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    out_dir, fields = argv[0], argv[1:] or FIELDS
    os.makedirs(out_dir, exist_ok=True)
    net.set_demo_mode(True)                 # only what is downloaded: validation never downloads
    _memo_skybot()
    runs = []
    for spec in fields:
        name, det = spec.rsplit(":", 1)
        for clip in (True, False):
            r = run_field(name, det, clip, out_dir)
            runs.append(r)
            found = [(x["rank"], x["pair"], x["type"], round(x["pm"], 2)) for x in r["found"]]
            print(f"{r['tag']}: {r['n']} candidates in {r['seconds']} s; target {found or 'not found'}; "
                  f"rest of field {r['rest']} ({r['rest_unexplained']} unexplained)", flush=True)
            json.dump(runs, open(os.path.join(out_dir, "validate_search.json"), "w"), indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
