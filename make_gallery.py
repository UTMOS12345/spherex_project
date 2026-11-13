"""Make every result for every challenge target, or say why it is missing.

    python make_gallery.py                 # from cache/ only (demo mode: no downloads)
    python make_gallery.py --only "RW Aur"
    python make_gallery.py --download      # also download missing frames (slow: ~9 s per frame)

For each target, demo/<target>/ gets one file per product below. A product that cannot be
made gets a placeholder picture instead, saying either
    NOT POSSIBLE  - e.g. the star is saturated, or SPHEREx has no such images, or
    POSSIBLE      - the images exist at IRSA but are not downloaded yet (how many).
A product made from only part of the images is marked PARTIAL (k of n frames).
demo/STATUS.md lists everything; demo/index.html shows it all in a browser.
Run prepare_demo.py first (it makes flipbook, difference, overlay, light curve, spectrum).
"""
import argparse
import html
import re
import textwrap
import time
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astropy.table import Table
from astropy.time import Time

warnings.simplefilter("ignore", RuntimeWarning)
from spherex import api, set_style
from spherex.download import find_cached
from spherex.epochs import assign_epochs
from spherex.frames import table_path
from spherex.targets import parse_target, at_time

OUT = Path("demo")
FOV = 4.0                    # arcmin, as prepare_demo.py
CUTOUT_DEG = 0.1             # the cutout size a 4' view uses
SECONDS_PER_DOWNLOAD = 9     # measured during prepare_demo.py runs
ALL = ["D1", "D2", "D3", "D4", "D5", "D6"]
# colour and difference pictures in which a saturated, filled-in core can look like a real signal
SATURATION_SENSITIVE = {"band_difference.png", "rgb.png", "minus_mean.gif", "flipbook_all.gif", "flipbook_D5+D6.gif"}
COLORS = {"READY": "#1baf7a", "PARTIAL": "#eda100", "POSSIBLE": "#eda100", "NOT POSSIBLE": "#7d7c76"}


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


# ---------------------------------------------------------------- what is cached
class Coverage:
    """Which frames of a target are in cache/ (at the size a 4' view needs)."""

    def __init__(self, name):
        self.target = parse_target(name)
        self.frames = assign_epochs(Table.read(table_path(name, self.target)))
        self.have = np.array([find_cached(r["access_url"], at_time(self.target, Time(r["mjd"], format="mjd")),
                                          CUTOUT_DEG) is not None for r in self.frames])

    def count(self, dets=None, latest_visit=False, band=None, tol=0.02):
        """(cached, total) frames for these detectors / the latest visit / a wavelength."""
        sel = np.ones(len(self.frames), bool)
        if dets is not None:
            sel &= np.isin(self.frames["detector"], dets)
        if latest_visit:
            sel &= self.frames["epoch"] == self.frames["epoch"].max()
        if band is not None:
            lo = np.asarray(self.frames["em_min"], float) * 1e6 - tol
            hi = np.asarray(self.frames["em_max"], float) * 1e6 + tol
            sel &= (lo <= band) & (band <= hi)
        return int((self.have & sel).sum()), int(sel.sum())


# ---------------------------------------------------------------- placeholders
def placeholder(path, title, status, message):
    """A picture that says why a product is missing, in the same dark style as the results."""
    fig = plt.figure(figsize=(7, 4.2))
    fig.text(0.05, 0.86, title, fontsize=14, fontweight="bold")
    fig.text(0.05, 0.72, status, fontsize=13, fontweight="bold", color=COLORS[status])
    fig.text(0.05, 0.62, "\n".join(textwrap.wrap(message, 70)), fontsize=10, va="top")
    fig.savefig(path)
    plt.close(fig)


def save(obj, path):
    """Save a figure (closing it) or GIF bytes."""
    if isinstance(obj, bytes):
        path.write_bytes(obj)
    else:
        obj.savefig(path, bbox_inches="tight")
        plt.close(obj)


# ---------------------------------------------------------------- the products
def products(name, cfg):
    """(file, title, frames-it-needs, how to make it) for one target. 'how' returns a figure,
    GIF bytes, or (figure, table); None in the frames field means 'made by prepare_demo.py'."""
    det, band, tol = cfg["detector"], cfg["band"], cfg["tol"]
    return [
        ("flipbook.gif", f"Video, {det}", None, None),
        ("difference.png", f"Last minus first visit, {det}", None, None),
        ("overlay.png", "Gaia + WISE overlay", None, None),
        ("lightcurve.png", f"Light curve at {band:g} ± {tol:g} µm", dict(band=band, tol=tol),
         lambda: api.light_curve_figure(name, band, tol)),
        ("spectrum.png", "Spectrum, latest visit", dict(latest_visit=True),
         lambda: api.spectrum_figure(name)),
        ("spectra_visits.png", "Spectrum of every visit", dict(),
         lambda: api.spectrum_figure(name, all_visits=True)),
        ("deep.png", f"All visits added, {det}", dict(dets=[det]),
         lambda: api.picture(name, "deep", detector=det, fov=FOV)),
        ("minus_mean.gif", f"Changes only: each visit minus the others, {det}", dict(dets=[det]),
         lambda: api.flipbook(name, det, FOV, mode="minusmean")),
        ("flipbook_D5+D6.gif", "Video, D5+D6 combined (3.8-5.0 µm)", dict(dets=["D5", "D6"]),
         lambda: api.flipbook(name, "D5+D6", FOV)),
        ("flipbook_all.gif", "Video, all six detectors combined", dict(dets=ALL),
         lambda: api.flipbook(name, "all", FOV)),
        ("band_difference.png", "Colour difference: D6 minus scaled D2", dict(dets=["D6", "D2"]),
         lambda: api.picture(name, "banddiff", fov=FOV, long="D6", short="D2")),
        ("rgb.png", "Colour picture: D6, D3, D1 as red, green, blue", dict(dets=["D6", "D3", "D1"]),
         lambda: api.picture(name, "rgb", fov=FOV, rgb="D6,D3,D1")),
    ]


def classify_failure(message, cached, total):
    """An API error -> (status, explanation)."""
    if "saturated" in message:
        return "NOT POSSIBLE", message
    missing = total - cached
    if total == 0:
        return "NOT POSSIBLE", f"SPHEREx has no images of this kind for this target. ({message})"
    if missing > 0:
        minutes = missing * SECONDS_PER_DOWNLOAD / 60
        return "POSSIBLE", (f"{missing} of {total} images it needs are at IRSA but not downloaded "
                            f"(about {minutes:.0f} min). Run: python make_gallery.py --download "
                            f"--only \"<target>\". Reason now: {message}")
    return "NOT POSSIBLE", message


def run_target(name, cfg, download):
    folder = OUT / safe_name(name)
    folder.mkdir(parents=True, exist_ok=True)
    cov = Coverage(name)
    rows = []
    saturated = False            # set once the light curve or spectrum fails for saturation (they come first)
    print(f"\n========== {name} ==========")
    for file, title, need, make in products(name, cfg):
        path = folder / file
        if make is None:                                   # made by prepare_demo.py
            rows.append((file, title, "READY" if path.exists() else "POSSIBLE",
                         "" if path.exists() else "Run python prepare_demo.py --skip-explore"))
            continue
        cached, total = cov.count(**need)
        t0 = time.time()
        try:
            result = make()
            fig, table = result if isinstance(result, tuple) else (result, None)
            save(fig, path)
            note = (table.meta.get("warning", "") if table is not None else "")
            if saturated and file in SATURATION_SENSITIVE:
                note = ("The target is saturated: its core is filled in from the pixels around it, "
                        "so its colour or brightness here is not a measurement.")
            full = download or cached == total
            status = "READY" if full else "PARTIAL"
            text = ("" if full else f"Made from the {cached} of {total} images in cache/; "
                    f"{total - cached} more are at IRSA (python make_gallery.py --download).")
            rows.append((file, title, status, " ".join(x for x in (text, note) if x)))
        except ValueError as e:
            status, text = classify_failure(str(e).replace("<target>", name), cached, total)
            text = text.replace("<target>", name)
            placeholder(path.with_suffix(".png") if path.suffix == ".gif" else path, title, status, text)
            if path.suffix == ".gif" and path.exists():
                path.unlink()                             # an old video would contradict the placeholder
            rows.append((path.with_suffix(".png").name if path.suffix == ".gif" else file, title, status, text))
        if rows[-1][2] == "NOT POSSIBLE" and "saturated" in rows[-1][3]:
            saturated = True
        print(f"  {rows[-1][2]:12s} {file:22s} ({time.time() - t0:.0f} s)")
    return rows


# ---------------------------------------------------------------- reports
def write_status(all_rows):
    lines = ["# Demo results: what is ready, partial, possible, or not possible", "",
             "Made by `make_gallery.py`. READY = made from every image; PARTIAL = made from the "
             "images in cache/ only; POSSIBLE = the images exist but are not downloaded; "
             "NOT POSSIBLE = cannot be measured (e.g. saturated). Open `index.html` to see them.", ""]
    for name, rows in all_rows.items():
        lines += [f"## {name}", "", "| Product | Status | Notes |", "|---|---|---|"]
        lines += [f"| {title} (`{file}`) | {status} | {note.replace('|', '/')} |" for file, title, status, note in rows]
        lines.append("")
    (OUT / "STATUS.md").write_text("\n".join(lines))


def write_html(all_rows):
    cards = []
    for name, rows in all_rows.items():
        folder = safe_name(name)
        items = "".join(
            f'<figure><img src="{folder}/{html.escape(f)}" loading="lazy" alt="{html.escape(t)}">'
            f'<figcaption><b>{html.escape(t)}</b> <span class="s" style="background:{COLORS[s]}">{s}</span>'
            f'<br><small>{html.escape(n)}</small></figcaption></figure>'
            for f, t, s, n in rows)
        cards.append(f"<section><h2>{html.escape(name)}</h2><div class='grid'>{items}</div></section>")
    (OUT / "index.html").write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>SPHEREx demo results</title>
<style>
:root {{ --bg:#1a1a19; --card:#232322; --ink:#f0efec; --muted:#c3c2b7; }}
body {{ background:var(--bg); color:var(--ink); font-family:system-ui, sans-serif; margin:0; padding:16px; }}
h1 {{ font-size:22px; }} h2 {{ font-size:18px; border-bottom:1px solid #383835; padding-bottom:4px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:14px; }}
figure {{ margin:0; background:var(--card); border-radius:8px; padding:8px; }}
img {{ width:100%; height:auto; border-radius:4px; background:#111; }}
figcaption {{ font-size:13px; margin-top:6px; color:var(--muted); }} figcaption b {{ color:var(--ink); }}
.s {{ color:#111; font-size:11px; font-weight:700; padding:1px 6px; border-radius:4px; margin-left:4px; }}
</style></head><body><h1>SPHEREx demo results</h1>
<p>Every product for every challenge target. Status: READY, PARTIAL (from the images in cache/ only),
POSSIBLE (images not downloaded yet), NOT POSSIBLE (e.g. saturated). Details in STATUS.md.</p>
{''.join(cards)}</body></html>
""")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="just this target")
    p.add_argument("--download", action="store_true", help="download missing frames (slow)")
    a = p.parse_args()
    api.set_demo_mode(not a.download)
    set_style(dark=True)
    todo = {k: v for k, v in api.DEMO_DEFAULTS.items() if not a.only or k.lower() == a.only.lower()}
    if not todo:
        raise SystemExit(f"unknown target; choose from {list(api.DEMO_DEFAULTS)}")
    all_rows = {}
    for name, cfg in todo.items():
        all_rows[name] = run_target(name, cfg, a.download)
    if not a.only:                                         # the reports cover all five targets
        write_status(all_rows)
        write_html(all_rows)
    print(f"\nresults in {OUT}/  (STATUS.md, index.html)")
