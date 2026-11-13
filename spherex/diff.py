"""Lesson 7 - difference images (epoch A minus epoch B) and the flipbook GIF."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from astropy.time import Time
from astropy.visualization import ZScaleInterval, AsinhStretch, ImageNormalize


def shared_norm(images):
    """One brightness scale (ZScale limits + Asinh stretch) for a whole list of images,
    so that a change between pictures is a real change and not a change of scale."""
    data = np.concatenate([im[np.isfinite(im)].ravel() for im in images])
    vmin, vmax = ZScaleInterval().get_limits(data)
    return ImageNormalize(vmin=vmin, vmax=vmax, stretch=AsinhStretch())


def difference(epoch_a, epoch_b, match_scale=False):
    """Two epochs from make_epochs (same grid) -> dict with image = A - B.
    Things that did not change cancel to ~0. A star that MOVED leaves a pair:
    positive where it is in A, negative where it was in B. A star that changed
    BRIGHTNESS leaves a single positive or negative spot.
    match_scale=True: first multiply B by one number so that the stars in B are as bright
    as in A (the median A/B ratio over bright pixels). Leave it off unless the two epochs
    clearly differ in overall brightness."""
    a, b = epoch_a["image"], epoch_b["image"]
    if a.shape != b.shape:
        raise ValueError("epochs are on different grids")
    scale = 1.0
    if match_scale:
        noise = 1.4826 * np.nanmedian(np.abs(b - np.nanmedian(b)))
        bright = np.isfinite(a) & np.isfinite(b) & (b > 10 * noise)   # pixels on stars
        if bright.sum() > 10:
            scale = float(np.median(a[bright] / b[bright]))
    return {"image": a - scale * b, "wcs": epoch_a["wcs"], "scale": scale,
            "detector": epoch_a["detector"],
            "label": f"{epoch_a['date']} minus {epoch_b['date']}",
            "mjd": epoch_a["mjd"], "date": epoch_a["date"],
            "mjd_a": epoch_a["mjd"], "mjd_b": epoch_b["mjd"]}


def make_gif(images, titles, out_path, fps=2, markers=None, norm=None, cmap="gray",
             mjds=None, max_hold=6):
    """List of 2D arrays (same shape) -> animated GIF, one picture per array.
    All pictures share one brightness scale. markers: optional list of (x, y) pixel
    positions, one per picture, drawn as a green circle.
    mjds: optional list of dates (MJD), one per picture. When given, the GIF shows real
    time: a timeline under the picture with a tick per picture and a red dot at "now",
    and each picture stays on screen longer when the gap to the next one is longer
    (up to max_hold times the shortest stay). No in-between pictures are invented."""
    norm = norm or shared_norm(images)
    n = len(images)
    order = list(range(n))                                 # which picture to show at each step
    if mjds is not None and n > 1:
        gaps = np.diff(np.asarray(mjds, float))
        shortest = max(gaps[gaps > 0].min(), 1e-6) if np.any(gaps > 0) else 1.0
        holds = [int(np.clip(round(g / shortest), 1, max_hold)) for g in gaps] + [max_hold]
        order = [i for i in range(n) for _ in range(holds[i])]

    if mjds is None:
        fig, ax = plt.subplots(figsize=(5, 5.3))
    else:
        fig, (ax, tl) = plt.subplots(2, 1, figsize=(5, 6.1), gridspec_kw={"height_ratios": [10, 1]})
        tl.vlines(mjds, 0, 1, color="0.5", lw=1)           # one tick per picture
        dot, = tl.plot([mjds[0]], [0.5], "o", color="red", ms=9)
        pad = 0.03 * (max(mjds) - min(mjds) or 1)
        tl.set_xlim(min(mjds) - pad, max(mjds) + pad); tl.set_ylim(0, 1); tl.set_yticks([])
        ends = [min(mjds), max(mjds)]
        tl.set_xticks(ends)
        tl.set_xticklabels([Time(m, format="mjd").iso[:10] for m in ends], fontsize=8)
    im = ax.imshow(images[0], origin="lower", cmap=cmap, norm=norm)
    ax.set_xticks([]); ax.set_yticks([])
    title = ax.set_title(titles[0], fontsize=10)
    ring = None
    if markers is not None:
        ring = ax.scatter([markers[0][0]], [markers[0][1]], s=400, facecolors="none", edgecolors="lime")

    def draw(step):
        i = order[step]
        im.set_data(images[i])
        title.set_text(titles[i])
        if ring is not None:
            ring.set_offsets([markers[i]])
        if mjds is not None:
            dot.set_data([mjds[i]], [0.5])
        return [im, title]

    FuncAnimation(fig, draw, frames=len(order)).save(out_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return out_path
