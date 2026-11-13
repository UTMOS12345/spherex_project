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
from spherex import (parse_detectors, parse_target, at_time, load_or_find_frames, assign_epochs, prefetch,
                     make_epochs, make_gif, difference, shared_norm, gaia_overlay, wise_overlay,
                     draw_gaia, light_curve, plot_light_curve_simple, spectrum, bin_to_channels,
                     epoch_frames, plot_spectrum, set_style)

# What to show for each target: the detector for pictures, the wavelength for the light curve.
TARGETS = {
    "Barnard's Star": dict(detector="D2", band=1.3, tol=0.05),   # moves fast; saturated -> no fluxes
    "WISE 0855":      dict(detector="D6", band=4.5, tol=0.10),   # cold brown dwarf: only seen at 4-5 um
    "Epsilon Indi B": dict(detector="D5", band=4.2, tol=0.10),   # brown dwarf pair, fast mover
    "RW Aur":         dict(detector="D1", band=0.9, tol=0.05),   # variable; saturates at 1.6 um
    "R Draconis":     dict(detector="D3", band=2.2, tol=0.10),   # pulsating red giant; may saturate
}
FIELD_ARCMIN = 4.0          # width of the pictures
OUT = Path("demo")


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
    titles = [f"{name}  {ep['detector']}  {ep['date']}  ({ep['n_frames']} frames)" for ep in epochs]
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
            (first["image"], f"B: {first['date']}", dict(cmap="gray", norm=norm)),
            (last["image"], f"A: {last['date']}", dict(cmap="gray", norm=norm)),
            (d["image"], "A - B  (red = brighter in A, blue = brighter in B)",
             dict(cmap="RdBu_r", vmin=-lim, vmax=lim))]):
        ax = fig.add_subplot(1, 3, i + 1, projection=d["wcs"])
        ax.imshow(img, origin="lower", **kw)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("RA"); ax.set_ylabel("Dec" if i == 0 else " ")
    fig.suptitle(f"{name}  {first['detector']}", x=0.02, ha="left", fontweight="bold")
    fig.savefig(folder / "difference.png", bbox_inches="tight")
    plt.close(fig)


def save_overlay(name, target, ep, folder, radius=0.15):   # 0.15 deg covers views up to ~15'
    t = Time(ep["mjd"], format="mjd")
    center = ep["wcs"].pixel_to_world(ep["image"].shape[1] / 2, ep["image"].shape[0] / 2)
    fig = plt.figure(figsize=(6.5, 6.5))
    ax = fig.add_subplot(projection=ep["wcs"])
    ax.imshow(ep["image"], origin="lower", cmap="gray", norm=shared_norm([ep["image"]]))
    notes = []
    for label, fn, kw in [("Gaia", gaia_overlay, {}),
                          ("WISE", wise_overlay, dict(color="#e87ba4", fast_color="#eb6834", marker="s"))]:
        try:
            draw_gaia(ax, fn(center, radius, t), ep["wcs"], ep["image"].shape, **kw)
            notes.append(label)
        except Exception as e:
            print(f"    {label} overlay skipped: {type(e).__name__}: {str(e)[:80]}")
    x, y = ep["wcs"].world_to_pixel(at_time(target, t))
    ax.scatter([x], [y], s=500, facecolors="none", edgecolors="lime", lw=1.2)
    ax.set_title(f"{name}  {ep['detector']}  {ep['date']}\n"
                 f"circles = Gaia, squares = WISE, arrows = next 5 years, green = target", fontsize=9)
    ax.set_xlabel("RA"); ax.set_ylabel("Dec")
    fig.savefig(folder / "overlay.png", bbox_inches="tight")
    plt.close(fig)
    if not notes:
        raise OSError("neither Gaia nor WISE could be reached")


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
    log.append(f"{name}: {len(frames)} frames, {frames['epoch'].max() + 1} visits")

    step("download cutouts", lambda: prefetch(needed_frames(frames, cfg, a.all_frames), target))
    state = {}

    def epochs():
        state["epochs"] = make_epochs(frames, target, cfg["detector"], grid_arcmin=FIELD_ARCMIN)
        if not state["epochs"]:
            raise RuntimeError(f"no {cfg['detector']} frames")
    step(f"stack visits ({cfg['detector']})", epochs)
    if state.get("epochs"):
        step("flipbook.gif + difference.png", lambda: save_flipbook_and_diff(name, target, state["epochs"], folder))
        step("overlay.png (Gaia + WISE)", lambda: save_overlay(name, target, state["epochs"][-1], folder))

    def lc():
        curve = light_curve(frames, target, cfg["band"], tol_um=cfg["tol"])
        curve.write(folder / "lightcurve.csv", overwrite=True)
        plot_light_curve_simple(curve, f"{name}: brightness at {cfg['band']:g} ± {cfg['tol']:g} µm",
                                folder / "lightcurve.png")
        log.append(f"        light curve: {len(curve)} points, {int(curve['ok'].sum()) if len(curve) else 0} usable")
    step(f"lightcurve ({cfg['band']} um)", lc)

    def sp():
        latest = epoch_frames(frames, -1)
        spec = spectrum(latest, target)
        binned = bin_to_channels(spec)
        spec.write(folder / "spectrum.csv", overwrite=True)
        plot_spectrum(spec, binned, f"{name}: spectrum, visit of {latest['date'][0][:10]}",
                      folder / "spectrum.png", log="auto")
        log.append(f"        spectrum: {len(spec)} points, {len(binned)} of 102 channels")
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
