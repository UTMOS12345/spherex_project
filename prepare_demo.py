"""Prepare the demo: download everything the five challenge targets need, then save a backup
copy of every result (GIF, difference, overlays, light curve, spectrum) in demo/<target>/.

    python prepare_demo.py                      # all five targets
    python prepare_demo.py --only "WISE 0855"   # one target
    python prepare_demo.py --refresh            # search IRSA again first (new data releases)
    python prepare_demo.py --all-frames         # download EVERY frame, not just the needed ones

Safe to stop (Ctrl+C) and run again: finished downloads are skipped. One failed step never
stops the rest; a summary is written to demo/SUMMARY.txt.
"""
import argparse
import os
import re
import time
import traceback
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astropy.time import Time

warnings.simplefilter("ignore", RuntimeWarning)
from spherex import (api, parse_detectors, parse_target, at_time, load_or_find_frames, assign_epochs, prefetch,
                     make_epochs, make_gif, difference, shared_norm, light_curve, spectrum,
                     epoch_frames, set_style)

from spherex.api import DEMO_DEFAULTS
from spherex.text import plural

# What to show for each target: the detector for pictures, the wavelength for the light curve.
# Shared with the app (spherex.api.DEMO_DEFAULTS), so the app's defaults are what is cached.
TARGETS = DEMO_DEFAULTS
FIELD_ARCMIN = 4.0          # width of the pictures
OUT = Path(os.environ.get("SPHEREX_DEMO_DIR", "demo"))


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def needed_frames(frames, cfg, all_frames):
    """Only the frames the demo uses: the picture detector (all visits), the light-curve band
    (all visits) and every detector of the latest visit (spectrum)."""
    if all_frames:
        return frames
    lo = np.asarray(frames["em_min"], float) * 1e6 - cfg["tol"]
    hi = np.asarray(frames["em_max"], float) * 1e6 + cfg["tol"]
    latest = set(epoch_frames(frames, -1)["access_url"])
    keep = (np.isin(frames["detector"], parse_detectors(cfg["detector"])) | ((lo <= cfg["band"]) & (cfg["band"] <= hi))
            | np.isin(frames["access_url"], list(latest)))
    return frames[keep]


def save_flipbook_and_diff(name, target, epochs, folder):
    images = [ep["image"] for ep in epochs]
    titles = [f"{name}  {ep['detector']}  {ep['date']}  ({plural(ep['n_frames'], 'frame')})" for ep in epochs]
    markers = [tuple(float(v) for v in ep["wcs"].world_to_pixel(at_time(target, Time(ep["mjd"], format="mjd"))))
               for ep in epochs]
    make_gif(images, titles, folder / "flipbook.gif", fps=3, markers=markers,
             mjds=[ep["mjd"] for ep in epochs])
    if len(epochs) < 2:
        return
    first, last = epochs[0], epochs[-1]
    d = difference(last, first)
    lim = np.nanpercentile(np.abs(d["image"]), 99.5)
    norm = shared_norm([first["image"], last["image"]])
    fig = plt.figure(figsize=(14, 4.8))
    for i, (img, title, kw) in enumerate([
            (first["image"], api._with_few(f"earlier: {first['date']}", first), dict(cmap="gray", norm=norm)),
            (last["image"], api._with_few(f"later: {last['date']}", last), dict(cmap="gray", norm=norm)),
            (d["image"], "later minus earlier  (red = brighter later, blue = brighter earlier)",
             dict(cmap="RdBu_r", vmin=-lim, vmax=lim))]):
        ax = fig.add_subplot(1, 3, i + 1, projection=d["wcs"])
        ax.imshow(img, origin="lower", **kw)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("RA"); ax.set_ylabel("Dec" if i == 0 else " ")
    fig.suptitle(f"{name}  {first['detector']}", x=0.02, ha="left", fontweight="bold")
    fig.savefig(folder / "difference.png", bbox_inches="tight")
    plt.close(fig)


def save_overlay(name, cfg, folder):
    """The app's own overlay (api.overlay_figure), so the backup shows what the app shows."""
    fig, notes = api.overlay_figure(name, cfg["detector"], FIELD_ARCMIN)
    fig.savefig(folder / "overlay.png", bbox_inches="tight")
    plt.close(fig)
    write_note(folder / "overlay_note.txt", notes.get("verdict"))
    if notes["failed"]:
        print(f"    overlay: not available: {notes['failed']}")
    if not notes["drawn"]:
        raise OSError("neither Gaia nor WISE could be reached")


def write_note(path, text):
    """Save a warning or message next to a backup picture; remove an old one if there is none."""
    if text:
        path.write_text(text + "\n")
    elif path.exists():
        path.unlink()


def run_target(name, cfg, a, log):
    folder = OUT / safe_name(name)
    folder.mkdir(parents=True, exist_ok=True)

    def step(label, fn):
        t0 = time.time()
        try:
            fn()
            log.append(f"  OK    {label}  ({time.time() - t0:.0f} s)")
        except Exception as e:
            log.append(f"  FAIL  {label}: {type(e).__name__}: {str(e)[:120]}")
            print(traceback.format_exc(limit=2))

    print(f"\n========== {name} ==========")
    target = parse_target(name)
    frames = assign_epochs(load_or_find_frames(name, target, refresh=a.refresh))
    log.append(f"{name}: {plural(len(frames), 'frame')}, {plural(frames['epoch'].max() + 1, 'visit')}")

    step("download cutouts", lambda: prefetch(needed_frames(frames, cfg, a.all_frames), target))
    state = {}

    def epochs():
        state["epochs"] = make_epochs(frames, target, cfg["detector"], grid_arcmin=FIELD_ARCMIN)
        if not state["epochs"]:
            raise RuntimeError(f"no {cfg['detector']} frames")
    step(f"stack visits ({cfg['detector']})", epochs)
    if state.get("epochs"):
        step("flipbook.gif + difference.png", lambda: save_flipbook_and_diff(name, target, state["epochs"], folder))
        step("overlay.png (Gaia + WISE)", lambda: save_overlay(name, cfg, folder))

    def lc():                        # the app's light curve; a saturated target gets a note, no picture
        try:
            fig, curve = api.light_curve_figure(name, cfg["band"], cfg["tol"])
            fig.savefig(folder / "lightcurve.png", bbox_inches="tight")
            plt.close(fig)
            note = curve.meta.get("warning")
        except ValueError as e:
            curve = light_curve(frames, target, cfg["band"], tol_um=cfg["tol"])
            (folder / "lightcurve.png").unlink(missing_ok=True)
            note = str(e)
        curve.write(folder / "lightcurve.csv", overwrite=True)
        write_note(folder / "lightcurve_note.txt", note)
        log.append(f"        light curve: {plural(len(curve), 'point')}, {int(curve['ok'].sum()) if len(curve) else 0} usable"
                   + (f"  [{note[:70]}]" if note else ""))
    step(f"light curve ({cfg['band']} um)", lc)

    def sp():                        # every measurement to CSV; the picture is the app's
        spec = spectrum(epoch_frames(frames, -1), target)
        spec.write(folder / "spectrum.csv", overwrite=True)
        try:
            fig, binned = api.spectrum_figure(name)
            fig.savefig(folder / "spectrum.png", bbox_inches="tight")
            plt.close(fig)
            note = binned.meta.get("warning")
            n = len({(d, c) for d, c, f in zip(binned["detector"], binned["channel"], binned["channel_flux_mjy"])
                     if np.isfinite(f)})                     # channels with an average
        except ValueError as e:
            (folder / "spectrum.png").unlink(missing_ok=True)
            note, n = str(e), 0
        write_note(folder / "spectrum_note.txt", note)
        log.append(f"        spectrum: {plural(len(spec), 'point')}, {n} of 102 channels" + (f"  [{note[:70]}]" if note else ""))
    step("spectrum (latest visit)", sp)

    def extra():                     # deep, differences, colour, spectra per visit, asteroids
        import sys
        import explore
        old = sys.argv
        sys.argv = ["explore.py", name, "--detector", cfg["detector"], "--fov", str(FIELD_ARCMIN)]
        try:
            explore.main()
        finally:
            sys.argv = old
    if not a.skip_explore:
        step("explore.py products -> out/" + safe_name(name), extra)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="run just this target")
    p.add_argument("--refresh", action="store_true", help="search IRSA again for new data")
    p.add_argument("--all-frames", action="store_true", help="download every frame of every detector")
    p.add_argument("--skip-explore", action="store_true", help="skip the extra explore.py products")
    a = p.parse_args()

    set_style(dark=True)
    todo = {k: v for k, v in TARGETS.items() if not a.only or k.lower() == a.only.lower()}
    if not todo:
        raise SystemExit(f"unknown target; choose from {list(TARGETS)}")
    OUT.mkdir(exist_ok=True)
    log, t0 = [], time.time()
    for name, cfg in todo.items():
        try:
            run_target(name, cfg, a, log)
        except Exception as e:                       # e.g. the frame search itself failed
            log.append(f"{name}: FAIL before start: {type(e).__name__}: {str(e)[:120]}")
        (OUT / "SUMMARY.txt").write_text("\n".join(log) + "\n")
    log.append(f"\ntotal time {(time.time() - t0) / 60:.1f} min")
    (OUT / "SUMMARY.txt").write_text("\n".join(log) + "\n")
    print("\n" + "\n".join(log))
    print(f"\nresults in {OUT}/, summary in {OUT}/SUMMARY.txt")
