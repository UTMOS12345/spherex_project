"""Explore a target: every way of adding and subtracting pictures, colour, spectra per visit,
and known asteroids. Results go to out/<target>/.

    python explore.py "WISE 0855"                         # everything, with sensible defaults
    python explore.py "WISE 0855" --detector D5+D6        # pictures from D5 and D6 combined
    python explore.py "Barnard's Star" --a 0 --b 2        # difference of visit 2 minus visit 0
    python explore.py "WISE 0855" --band-diff D6,D2       # colour difference: D6 minus scaled D2
    python explore.py "WISE 0855" --rgb D6,D3,D1          # colour picture: red, green, blue
    python explore.py "R Draconis" --only spectra         # just one product

Products (--only one of these):
    deep        all visits ADDED            -> deep.png
    pair        visit A MINUS visit B       -> pair_difference.png
    series      each visit MINUS the first  -> difference_series.gif
    minusmean   each visit MINUS the others -> minus_mean.gif
    banddiff    long colour MINUS short     -> band_difference.png
    rgb         three colours as R, G, B    -> rgb.png
    spectra     spectrum of every visit     -> spectra_visits.png
    asteroids   known asteroids/comets      -> asteroids.png
"""
import argparse
import os
import re
import traceback
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astropy.time import Time

warnings.simplefilter("ignore", RuntimeWarning)
from spherex.text import plural
from spherex import (parse_target, at_time, load_or_find_frames, assign_epochs, make_epochs,
                     difference, make_gif, shared_norm, deep_image, minus_mean, difference_series,
                     band_difference, rgb_image, spectrum, bin_to_channels, plot_spectra_visits,
                     known_asteroids, draw_asteroids, set_style)

PRODUCTS = ["deep", "pair", "series", "minusmean", "banddiff", "rgb", "spectra", "asteroids"]


def marker(target, ep):
    return tuple(float(v) for v in ep["wcs"].world_to_pixel(at_time(target, Time(ep["mjd"], format="mjd"))))


def show(ep, title, path, target=None, diverging=False):
    """One picture with RA/Dec axes; diverging=True for differences (red +, blue -)."""
    fig = plt.figure(figsize=(6.2, 6.2))
    ax = fig.add_subplot(projection=ep["wcs"])
    img = ep["image"]
    if diverging:
        lim = np.nanpercentile(np.abs(img), 99.5) or 1
        ax.imshow(img, origin="lower", cmap="RdBu_r", vmin=-lim, vmax=lim)
    else:
        ax.imshow(img, origin="lower", cmap="gray", norm=shared_norm([img]))
    if target is not None:
        x, y = marker(target, ep)
        ax.scatter([x], [y], s=450, facecolors="none", edgecolors="lime", lw=1.2)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("RA"); ax.set_ylabel("Dec")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print("  saved", path)


def gif(eps, target, name, path, diverging=False):
    imgs = [e["image"] for e in eps]
    norm = None
    if diverging:
        from matplotlib.colors import Normalize
        lim = np.nanpercentile(np.abs(np.concatenate([i[np.isfinite(i)] for i in imgs])), 99.5) or 1
        norm = Normalize(-lim, lim)
    make_gif(imgs, [f"{name}  {e['label']}" for e in eps], path, fps=2,
             markers=[marker(target, e) for e in eps], norm=norm,
             cmap="RdBu_r" if diverging else "gray", mjds=[e["mjd"] for e in eps])
    print("  saved", path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("target")
    p.add_argument("--detector", default=None, help="pictures from D1..D6, D5+D6, all (default: chosen per target)")
    p.add_argument("--fov", type=float, default=4.0, help="field of view in arcmin (up to ~10)")
    p.add_argument("--a", type=int, default=-1, help="one visit of the pair difference (default: last); the later one is shown minus the earlier")
    p.add_argument("--b", type=int, default=0, help="the other visit of the pair difference (default: first)")
    p.add_argument("--band-diff", default="D6,D2", help="long,short detectors for the colour difference")
    p.add_argument("--rgb", default="D6,D3,D1", help="red,green,blue detectors")
    p.add_argument("--only", choices=PRODUCTS, help="make just one product")
    p.add_argument("--light", action="store_true", help="light theme instead of dark")
    a = p.parse_args()

    set_style(dark=not a.light)
    target = parse_target(a.target)
    frames = assign_epochs(load_or_find_frames(a.target, target))
    name = a.target
    folder = Path(os.environ.get("SPHEREX_OUT_DIR", "out")) / re.sub(r"[^A-Za-z0-9]+", "_", a.target).strip("_")
    folder.mkdir(parents=True, exist_ok=True)
    todo = [a.only] if a.only else PRODUCTS
    det = a.detector or "D2"
    cache = {}

    def epochs(d):                     # stacks per detector choice, made once and reused
        if d not in cache:
            cache[d] = make_epochs(frames, target, d, grid_arcmin=a.fov)
        return cache[d]

    def run(product, fn):
        if product not in todo:
            return
        print(f"\n[{product}]")
        try:
            fn()
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {str(e)[:150]}")
            traceback.print_exc(limit=1)

    def do_deep():
        eps = epochs(det)
        dp = deep_image(eps)
        show(dp, f"{name}  {det}  {dp['label']}\n({plural(dp['n_frames'], 'frame')}, {dp['date']})", folder / "deep.png", target)

    def do_pair():
        eps = epochs(det)
        later, earlier = sorted([eps[a.a], eps[a.b]], key=lambda e: e["mjd"], reverse=True)
        d = difference(later, earlier)
        show(d, f"{name}  {det}  later minus earlier: {d['label']}\nred = brighter later, blue = brighter earlier",
             folder / "pair_difference.png", target, diverging=True)

    def do_series():
        eps = epochs(det)
        gif(difference_series(eps), target, f"{name} {det}", folder / "difference_series.gif", diverging=True)

    def do_minusmean():
        eps = epochs(det)
        if len(eps) < 2:
            raise RuntimeError("needs at least 2 visits")
        gif(minus_mean(eps), target, f"{name} {det}", folder / "minus_mean.gif", diverging=True)

    def do_banddiff():
        long_d, short_d = a.band_diff.split(",")
        L, S = epochs(long_d.strip()), epochs(short_d.strip())
        common = sorted(set(e["epoch"] for e in L) & set(e["epoch"] for e in S))
        if not common:
            raise RuntimeError(f"no visit has both {long_d} and {short_d}")
        e = common[-1]
        d = band_difference([x for x in L if x["epoch"] == e][0], [x for x in S if x["epoch"] == e][0])
        show(d, f"{name}  {d['label']}\nred = brighter in {long_d.strip()}, blue = brighter in scaled {short_d.strip()} "
                "(normal stars cancel)",
             folder / "band_difference.png", target, diverging=True)

    def do_rgb():
        dets = [x.strip() for x in a.rgb.split(",")]
        sets = [epochs(d) for d in dets]
        common = sorted(set.intersection(*[set(e["epoch"] for e in s) for s in sets]))
        if not common:
            raise RuntimeError(f"no visit has all of {dets}")
        e = common[-1]
        r, g, b = ([x for x in s if x["epoch"] == e][0] for s in sets)
        rgb = rgb_image(r["image"], g["image"], b["image"])
        fig = plt.figure(figsize=(6.2, 6.2))
        ax = fig.add_subplot(projection=r["wcs"])
        ax.imshow(rgb, origin="lower")
        x, y = marker(target, r)
        ax.scatter([x], [y], s=450, facecolors="none", edgecolors="white", lw=1)
        ax.set_title(f"{name}  {r['date']}\nred = {dets[0]}, green = {dets[1]}, blue = {dets[2]}", fontsize=10)
        ax.set_xlabel("RA"); ax.set_ylabel("Dec")
        fig.savefig(folder / "rgb.png", bbox_inches="tight")
        plt.close(fig)
        print("  saved", folder / "rgb.png")

    def do_spectra():
        per_visit = []
        for e in sorted(set(frames["epoch"])):
            sub = frames[frames["epoch"] == e]
            b = bin_to_channels(spectrum(sub, target))
            print(f"  visit {e} ({sub['date'][0][:10]}): {plural(len(b), 'channel')} with usable data")
            per_visit.append((sub["date"][0][:10], b))
        plot_spectra_visits(per_visit, f"{name}: spectrum of every visit", folder / "spectra_visits.png")
        print("  saved", folder / "spectra_visits.png")

    def do_asteroids():
        ep = epochs(det)[-1]
        t = Time(ep["mjd"], format="mjd")
        center = ep["wcs"].pixel_to_world(ep["image"].shape[1] / 2, ep["image"].shape[0] / 2)
        objs = known_asteroids(center, a.fov / 60 * 0.75, t)
        fig = plt.figure(figsize=(6.2, 6.2))
        ax = fig.add_subplot(projection=ep["wcs"])
        ax.imshow(ep["image"], origin="lower", cmap="gray", norm=shared_norm([ep["image"]]))
        n = draw_asteroids(ax, objs, ep["wcs"], ep["image"].shape)
        ax.set_title(f"{name}  {det}  {ep['date']}\nknown asteroids/comets: {n} in view", fontsize=10)
        ax.set_xlabel("RA"); ax.set_ylabel("Dec")
        fig.savefig(folder / "asteroids.png", bbox_inches="tight")
        plt.close(fig)
        print(f"  {plural(n, 'known solar-system object')} in view; saved", folder / "asteroids.png")

    for product, fn in [("deep", do_deep), ("pair", do_pair), ("series", do_series),
                        ("minusmean", do_minusmean), ("banddiff", do_banddiff), ("rgb", do_rgb),
                        ("spectra", do_spectra), ("asteroids", do_asteroids)]:
        run(product, fn)
    print(f"\nresults in {folder}/")


if __name__ == "__main__":
    main()
