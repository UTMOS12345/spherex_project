"""Lesson 5 (with exercise solutions): flags, ZODI, cleaning.

    python lesson5_clean.py                       # uses the cutouts in cache/cutouts/
    python lesson5_clean.py cache/cutouts/X.fits  # detailed look at one chosen file
"""
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")                      # save PNGs, no window (no tkinter needed)
import matplotlib.pyplot as plt
from astropy.visualization import ZScaleInterval, AsinhStretch, ImageNormalize

from spherex import clean_frame, decode_flags, check_cache, CACHE_DIR, BAD_FLAGS


def flag_census(f):
    """Exercise 1: % of pixels with each flag set."""
    print("\n1) flag census (% of pixels):")
    for name, b in sorted(f["bits"].items(), key=lambda kv: kv[1]):
        pct = ((f["flags"] & (1 << b)) != 0).mean() * 100
        note = "masked" if name in BAD_FLAGS else "kept"
        print(f"   bit {b:2d}  {name:16s} {pct:6.2f}%   ({note})")
    print(f"   total masked: {f['bad'].mean() * 100:.2f}%")


def medians_per_detector(paths):
    """Exercise 2: raw / zodi / clean medians for one cutout per detector."""
    print("\n2) medians per detector (MJy/sr):")
    print("   det      raw     zodi    clean   masked%")
    seen = {}
    for p in paths:
        f = clean_frame(p)
        det = int(f["header"]["DETECTOR"])
        if det not in seen:
            seen[det] = f
    for det in sorted(seen):
        f = seen[det]
        print(f"   D{det}  {np.nanmedian(f['raw']):8.3f} {np.nanmedian(f['zodi']):8.3f} "
              f"{np.nanmedian(f['image']):8.3f} {f['bad'].mean() * 100:8.2f}")
    return seen


def star_flags(f, half=2):
    """Exercise 3: flags on the star (centre pixel and the 5x5 box around it)."""
    ny, nx = f["image"].shape
    cy, cx = ny // 2, nx // 2
    print("\n3) the star (cutout centre):")
    print("   centre pixel flags:", decode_flags(f["flags"][cy, cx], f["bits"]) or "none")
    box_bad = f["bad"][cy - half: cy + half + 1, cx - half: cx + half + 1]
    box_flags = f["flags"][cy - half: cy + half + 1, cx - half: cx + half + 1]
    print(f"   masked pixels in the central {2 * half + 1}x{2 * half + 1} box: {box_bad.sum()} of {box_bad.size}")
    causes = {}
    for v in box_flags[box_bad]:
        for name in decode_flags(v, f["bits"]):
            if name in BAD_FLAGS:
                causes[name] = causes.get(name, 0) + 1
    if causes:
        print("   caused by:", causes, "-> the star's core is damaged in this frame")
    else:
        print("   core is clean in this frame")


def three_panels(f, out_png):
    """Exercise 4: raw | zodi | cleaned, masked pixels in red."""
    cmap = plt.get_cmap("gray").copy()
    cmap.set_bad("red")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))
    for ax, key, title in zip(axes, ["raw", "zodi", "image"],
                              ["IMAGE (raw)", "ZODI (model)", "IMAGE - ZODI, bad = red"]):
        data = f[key]
        good = np.isfinite(data)
        vmin, vmax = ZScaleInterval().get_limits(data[good])
        if vmax <= vmin:                       # ZODI can be almost perfectly flat
            vmin, vmax = np.nanmin(data) - 0.01, np.nanmax(data) + 0.01
        ax.imshow(data, origin="lower", cmap=cmap,
                  norm=ImageNormalize(vmin=vmin, vmax=vmax, stretch=AsinhStretch()))
        ax.set_title(f"{title}\nmedian {np.nanmedian(data):.3f} MJy/sr", fontsize=9)
    fig.suptitle(f"D{f['header']['DETECTOR']}  MJD {f['mjd']:.2f}", fontsize=10)
    fig.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\n4) saved {out_png}")


if __name__ == "__main__":
    n_valid, bad_files = check_cache()
    paths = [p for p in sorted(CACHE_DIR.glob("*.fits")) if p not in bad_files]
    if not paths and len(sys.argv) < 2:
        sys.exit("No cutouts in cache/cutouts/ - run lesson4_cache.py first.")

    if len(sys.argv) > 1:
        chosen = clean_frame(sys.argv[1])
    else:                                      # prefer a D2 cutout, as the exercise asks
        frames = [clean_frame(p) for p in paths]
        d2 = [f for f in frames if int(f["header"]["DETECTOR"]) == 2]
        chosen = d2[0] if d2 else frames[0]

    print(f"detailed file: detector D{chosen['header']['DETECTOR']}, MJD {chosen['mjd']:.2f}")
    print("flag bits in this file:", chosen["bits"])
    flag_census(chosen)
    if paths:
        medians_per_detector(paths)
    star_flags(chosen)
    Path("out").mkdir(exist_ok=True)
    three_panels(chosen, "out/lesson5_panels.png")
