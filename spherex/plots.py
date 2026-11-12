"""Nicer pictures for the app: the light curve, one panel per visit."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astropy.time import Time

LIGHT = dict(blue="#2a78d6", ink="#0b0b0b", muted="#52514e", grid="#e6e5e1", surface="#fcfcfb", flag="#a3a29c")
DARK = dict(blue="#3987e5", ink="#f0efec", muted="#c3c2b7", grid="#383835", surface="#1a1a19", flag="#7d7c76")
THEME = dict(LIGHT)


def set_style(dark=False):
    """One look for EVERY matplotlib figure made after this call (images, GIFs, plots):
    same font, same text colours, same background. dark=True suits sky images."""
    THEME.clear(); THEME.update(DARK if dark else LIGHT)
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
        "figure.facecolor": THEME["surface"], "axes.facecolor": THEME["surface"],
        "savefig.facecolor": THEME["surface"],
        "text.color": THEME["ink"], "axes.titlecolor": THEME["ink"],
        "axes.labelcolor": THEME["muted"], "xtick.color": THEME["muted"], "ytick.color": THEME["muted"],
        "axes.edgecolor": THEME["grid"], "grid.color": THEME["grid"],
        "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "figure.dpi": 110, "savefig.dpi": 140,
    })


def plot_light_curve(lc, title, out_png=None, gap_days=30):
    """Light-curve table from light_curve() -> figure with ONE PANEL PER VISIT.
    Visits are months apart but only days long, so on a single time axis the points pile
    up into thin stripes. Here each visit gets its own panel (same flux scale in all),
    so every point is visible and the visits can still be compared by eye.
    Blue dot = usable point with its error bar, grey x = flagged point,
    line = the visit's mean, with the change since the first visit written next to it."""
    BLUE, INK, MUTED, GRID, SURFACE = (THEME[k] for k in ("blue", "ink", "muted", "grid", "surface"))
    lc = lc.copy()
    lc.sort("mjd")
    visit = np.concatenate([[0], np.cumsum(np.diff(lc["mjd"]) > gap_days)])
    ids = sorted(set(visit))
    fig, axes = plt.subplots(1, len(ids), figsize=(3.4 * len(ids) + 1.2, 4.3), sharey=True,
                             squeeze=False, facecolor=SURFACE)
    good_all = lc[lc["ok"]]
    first_mean = None
    for ax, v in zip(axes[0], ids):
        rows = lc[visit == v]
        t0 = np.floor(rows["mjd"].min())                       # day the visit starts
        good, bad = rows[rows["ok"]], rows[~rows["ok"]]
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, lw=1); ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=MUTED, length=0, labelsize=9)
        if len(bad):
            ax.plot(bad["mjd"] - t0, bad["flux_mjy"], "x", color=THEME["flag"], ms=7, mew=1.5,
                    label="flagged (not used)")
        if len(good):
            ax.errorbar(good["mjd"] - t0, good["flux_mjy"], yerr=good["err_mjy"], fmt="o",
                        color=BLUE, ms=8, mec=SURFACE, mew=2, elinewidth=1.5, capsize=0,
                        label="measurement")
            mean = float(np.mean(good["flux_mjy"]))
            ax.axhline(mean, color=BLUE, lw=2, alpha=0.35)
            note = f"mean {mean:,.1f} mJy"
            if first_mean is None:
                first_mean = mean
            elif first_mean > 0:
                note += f"\n{(mean / first_mean - 1) * 100:+.0f}% vs first visit"
            ax.annotate(note, xy=(0.03, mean), xycoords=("axes fraction", "data"),
                        xytext=(0, 6), textcoords="offset points", fontsize=9, color=INK, va="bottom")
        else:
            ax.text(0.5, 0.5, "no usable\nmeasurement", transform=ax.transAxes, ha="center",
                    va="center", color=MUTED, fontsize=10)
        span = max(rows["mjd"].max() - t0, 1)
        ax.set_xlim(-0.08 * span, 1.08 * span)
        ax.set_title(Time(t0, format="mjd").strftime("%d %b %Y"), fontsize=11, color=INK, loc="left")
        ax.set_xlabel("days into the visit", fontsize=9, color=MUTED)
    axes[0][0].set_ylabel("flux (mJy)", fontsize=10, color=MUTED)
    if len(good_all):
        lo, hi = good_all["flux_mjy"].min(), good_all["flux_mjy"].max()
        pad = 0.25 * (hi - lo) or 0.1 * abs(hi) or 1
        axes[0][0].set_ylim(min(lo - pad, lo * 0.9), hi + 1.6 * pad)   # scale set by the usable points
    handles, labels = [], []
    for ax in axes[0]:
        for h, l in zip(*ax.get_legend_handles_labels()):
            if l not in labels:
                handles.append(h); labels.append(l)
    if len(labels) > 1:
        fig.legend(handles, labels, loc="upper right", fontsize=9, frameon=False, ncol=2,
                   labelcolor=MUTED)
    fig.suptitle(title, x=0.02, ha="left", fontsize=13, color=INK, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    if out_png:
        fig.savefig(out_png, dpi=140, facecolor=SURFACE)
        plt.close(fig)
    return fig


def plot_light_curve_simple(lc, title, out_png=None, gap_days=30):
    """The easy-to-read light curve: ONE axis, x = date, y = brightness.
    Big dot = the average of one visit (bar = spread of that visit's points),
    small dots = the single usable measurements, a line joins the visits.
    A visit with no usable point is marked at the bottom with the reason."""
    B, INK, MUTED, GRID = THEME["blue"], THEME["ink"], THEME["muted"], THEME["grid"]
    lc = lc.copy()
    lc.sort("mjd")
    visit = np.concatenate([[0], np.cumsum(np.diff(lc["mjd"]) > gap_days)])
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.grid(axis="y", lw=1); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(length=0)
    dates, means, spreads, empty = [], [], [], []
    for v in sorted(set(visit)):
        rows = lc[visit == v]
        good = rows[rows["ok"]]
        d = Time(np.mean(rows["mjd"]), format="mjd").datetime
        if len(good) == 0:
            reason = "saturated" if rows["saturated"].any() else "bad pixels"
            empty.append((d, reason))
            continue
        ax.plot(Time(good["mjd"], format="mjd").datetime, good["flux_mjy"], "o", color=B, ms=4, alpha=0.45)
        dates.append(d)
        means.append(float(np.mean(good["flux_mjy"])))
        spreads.append(float(np.std(good["flux_mjy"])) if len(good) > 1 else float(good["err_mjy"][0]))
    if dates:
        ax.plot(dates, means, "-", color=B, lw=2, alpha=0.6)
        ax.errorbar(dates, means, yerr=spreads, fmt="o", color=B, ms=11, mec=THEME["surface"], mew=2,
                    elinewidth=2, capsize=0, label="visit average (bar = spread)")
        for d, m in zip(dates, means):
            ax.annotate(f"{m:,.0f}", (d, m), xytext=(10, 0), textcoords="offset points",
                        va="center", fontsize=9, color=INK)
        ax.set_ylim(0, max(np.array(means) + np.array(spreads)) * 1.3)
    else:
        ax.set_ylim(0, 1)
    for d, reason in empty:
        ax.annotate(f"no usable data\n({reason})", (d, 0), xytext=(0, 8), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9, color=MUTED)
        ax.plot([d], [0], marker="x", color=THEME["flag"], ms=9, mew=2, clip_on=False)
    ax.set_ylabel("brightness (mJy)")
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    if dates:
        ax.legend(loc="upper left", fontsize=9, labelcolor=MUTED)
    fig.autofmt_xdate()
    fig.tight_layout()
    if out_png:
        fig.savefig(out_png)
        plt.close(fig)
    return fig


def plot_spectrum(spec, binned, title, out_png=None, log=False):
    """Spectrum table (from spectrum()) + channel table (from bin_to_channels()) -> figure.
    Light/dark bands mark the six detectors. Small dots = single measurements,
    big dots joined by a line = the average in each of the 102 channels, grey x = flagged."""
    from .spectrum import BANDS_UM
    B, INK, MUTED, GRID = THEME["blue"], THEME["ink"], THEME["muted"], THEME["grid"]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.grid(axis="y", lw=1); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(length=0)
    for d, (lo, hi) in BANDS_UM.items():
        if d % 2 == 0:
            ax.axvspan(lo, hi, color=GRID, alpha=0.35, lw=0)
        ax.text((lo + hi) / 2, 1.01, f"D{d}", transform=ax.get_xaxis_transform(), ha="center",
                va="bottom", fontsize=9, color=MUTED)
    good, bad = spec[spec["ok"]], spec[~spec["ok"]]
    if len(good):
        ax.errorbar(good["wavelength_um"], good["flux_mjy"], yerr=good["err_mjy"], fmt="o", color=B,
                    ms=3, alpha=0.35, elinewidth=1, capsize=0, label="single measurement")
    if len(binned):
        for d in sorted(set(binned["detector"])):              # no line across detector gaps
            b = binned[binned["detector"] == d]
            ax.plot(b["wavelength_um"], b["flux_mjy"], "-", color=B, lw=2)
        ax.errorbar(binned["wavelength_um"], binned["flux_mjy"], yerr=binned["err_mjy"], fmt="o",
                    color=B, ms=7, mec=THEME["surface"], mew=1.5, elinewidth=1.5, capsize=0,
                    label="channel average")
    if len(good):
        lo, hi = np.nanmin(good["flux_mjy"]), np.nanmax(good["flux_mjy"])
        if log and hi > 0:
            ax.set_yscale("log")
            ax.set_ylim(max(lo, hi * 1e-3) * 0.5, hi * 2)
        else:
            pad = 0.1 * (hi - lo) or 0.1 * abs(hi) or 1
            ax.set_ylim(min(0, lo - pad), hi + 2 * pad)
    if len(bad):
        y0 = ax.get_ylim()[0]
        ax.plot(bad["wavelength_um"], np.full(len(bad), y0), "x", color=THEME["flag"], ms=7, mew=1.5,
                clip_on=False, label=f"flagged, not used ({len(bad)})")
    ax.set_xlim(0.72, 5.03)
    ax.set_xlabel("wavelength (µm)"); ax.set_ylabel("brightness (mJy)")
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=18)
    ax.legend(loc="upper left", fontsize=9, labelcolor=MUTED)
    fig.tight_layout()
    if out_png:
        fig.savefig(out_png)
        plt.close(fig)
    return fig
