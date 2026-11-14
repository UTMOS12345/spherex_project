"""The app's menu: one function per feature. Inputs are plain text and numbers; outputs are
things a web app can show directly - a matplotlib figure, GIF bytes, or a table.

    from spherex import api
    info = api.resolve("WISE 0855")
    gif  = api.flipbook("WISE 0855", detector="D5+D6", fov=6)          # bytes -> st.image(gif)
    fig  = api.picture("WISE 0855", kind="rgb")                         # figure -> st.pyplot(fig)
    fig, table = api.light_curve_figure("RW Aur", band=0.9)

Every function raises ValueError with a readable message for bad input (unknown name,
unknown detector, no data), so the app can show it with st.error(str(e)).
Slow on first use for a new target (downloads); fast afterwards (disk cache + memory cache).
"""
import os
import tempfile

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time

from .asteroids import known_asteroids, draw_asteroids
from .clean import clean_frame, BAD_FLAGS
from .combine import deep_image, minus_mean, difference_series, band_difference, rgb_image
from .diff import difference, make_gif, shared_norm
from .download import get_cutout
from .epochs import assign_epochs, make_epochs, parse_detectors, CLIP_MIN_FRAMES
from .frames import load_or_find_frames
from .gaia import gaia_overlay, draw_gaia
from .photometry import light_curve
from .plots import (plot_light_curve_simple, plot_spectrum, plot_spectra_visits, wavelength_spread, WL_SPREAD_UM,
                    THEME)
from .spectrum import spectrum, bin_to_channels, channel_edges
from .targets import parse_target, at_time, has_pm, known_target, known_near, target_name
from .wise import wise_overlay
from . import net
from .net import set_demo_mode            # api.set_demo_mode(True): cached data only, no hangs

MAX_FOV = 10.0            # arcmin served from the standard downloads
_memory = {}              # stacks already made in this process: key -> list of epochs

# Settings whose images prepare_demo.py downloads for the challenge targets: with these the
# app runs from cache/ without downloads. prepare_demo.py reads this table too.
DEMO_DEFAULTS = {
    "Barnard's Star": dict(detector="D2", band=1.3, tol=0.02),   # moves fast; saturated -> no fluxes
    "WISE 0855":      dict(detector="D6", band=4.5, tol=0.02),   # cold brown dwarf: only seen at 4-5 um
    "Epsilon Indi B": dict(detector="D5", band=4.2, tol=0.02),   # brown dwarf pair, fast mover
    "RW Aur":         dict(detector="D1", band=0.9, tol=0.02),   # variable; saturates at 1.6 um
    "R Draconis":     dict(detector="D3", band=2.2, tol=0.02),   # pulsating red giant; saturated
}
OTHER_DEFAULTS = dict(detector="D2", band=1.6, tol=0.02)
MAX_SAFE_TOL = 0.05       # light curves with a wider wavelength window get a warning
# tol 0.02 um: a wider window mixes wavelengths, and across a steep spectrum that looks like
# variability (Epsilon Indi B: 57 vs 35 mJy at 4.10 vs 4.25 um in ONE visit).


def demo_mode():
    """True when demo mode is on (no downloads; one short try per server call)."""
    return net.DEMO_MODE


def defaults(text):
    """Suggested detector, light-curve band and tolerance for a target -> dict.
    For the five challenge targets these are the settings already in cache/."""
    try:
        name = target_name(text, parse_target(text))
    except ValueError:
        return dict(OTHER_DEFAULTS)
    return dict(DEMO_DEFAULTS.get(name, OTHER_DEFAULTS))


# ------------------------------------------------------------------ helpers
def _parse(text):
    try:
        return parse_target(text)
    except ValueError:
        raise ValueError(f"Could not find '{text}'. Check the spelling, or enter coordinates "
                         f"like '133.795 -7.245' or '08h55m10.8s -07d14m42.5s'.")


def _load(text, refresh=False):
    target = _parse(text)
    frames = load_or_find_frames(text, target, refresh=refresh)
    if len(frames) == 0:
        raise ValueError(f"SPHEREx has no images of '{text}' yet.")
    return target, assign_epochs(frames)


def _wl(wl):
    """'4.4-4.7' or (4.4, 4.7) or None -> tuple or None."""
    if wl in (None, "", ()):
        return None
    if isinstance(wl, str):
        try:
            wl = [float(v) for v in wl.replace(",", "-").split("-")]
        except ValueError:
            raise ValueError("Wavelength range must look like '4.4-4.7' (micron).")
    if len(wl) != 2 or not 0.7 <= min(wl) < max(wl) <= 5.1:
        raise ValueError("Wavelength range must be two numbers between 0.75 and 5.0 micron.")
    return (float(min(wl)), float(max(wl)))


def _epochs(text, detector="D2", fov=4.0, wl=None, days=60, clip=True):
    """Stacked visits (memory-cached). detector may be None when wl is given.
    clip=False: plain average of the frames (see epochs.stack_epoch)."""
    if not 1 <= fov <= MAX_FOV:            # larger views would need new, bigger downloads of every frame
        raise ValueError(f"Field of view must be between 1 and {MAX_FOV:g} arcmin.")
    wl = _wl(wl)
    try:
        days = float(days)
    except (TypeError, ValueError):
        raise ValueError("days must be a number: 60 (one picture per visit), 30, 7, or 0 (every frame).")
    if days < 0:
        raise ValueError("days must be 0 (every frame) or more.")
    days = int(days) if days == int(days) else days
    det = None if (wl and not detector) else "+".join(parse_detectors(detector or "D2"))
    target, frames = _load(text)
    # the frame URLs are part of the key: a refresh that swaps releases rebuilds the stacks
    key = (target_name(text, target), det, round(float(fov), 2), wl, days, bool(clip),
           hash(tuple(frames["access_url"])))
    if key not in _memory:
        eps = make_epochs(frames, target, det, grid_arcmin=fov, wl_range=wl,
                          gap_days=min(30, days), max_len_days=days, clip=clip)
        if not eps:
            if net.DEMO_MODE:
                raise ValueError(f"The {det or 'matching'} images of '{text}' are not in the offline cache. "
                                 "Untick demo mode to download them (this takes minutes).")
            raise ValueError(f"No usable {det or 'matching'} images of '{text}'"
                             + (f" at {wl[0]}-{wl[1]} micron." if wl else "."))
        if len(_memory) > 40:
            _memory.pop(next(iter(_memory)))
        _memory[key] = eps
    return target, frames, _memory[key]


FEW_FRAMES_NOTE = "few frames: unreliable"


def _few(*eps):
    """'few frames: unreliable' if any of these stacks rests on fewer than CLIP_MIN_FRAMES frames
    somewhere in its centre (outliers then cannot be rejected), else ''."""
    return FEW_FRAMES_NOTE if any(e.get("n_min", CLIP_MIN_FRAMES) < CLIP_MIN_FRAMES for e in eps) else ""


def _with_few(title, *eps):
    note = _few(*eps)
    return f"{title}\n{note}" if note else title


def _choose(eps, pictures):
    """pictures (None, or row numbers of api.epochs for the same settings) -> sorted row numbers.
    The pictures are in time order, so sorted row numbers keep time order."""
    if pictures is None:
        return list(range(len(eps)))
    try:
        idx = sorted({int(i) for i in pictures})
    except (TypeError, ValueError):
        raise ValueError("pictures must be a list of row numbers from api.epochs, like [0, 2, 5].")
    if not idx:
        raise ValueError("Choose at least one picture.")
    bad = [i for i in idx if not 0 <= i < len(eps)]
    if bad:
        raise ValueError(f"There are only {len(eps)} pictures with these settings (rows 0..{len(eps) - 1}); "
                         f"{', '.join(map(str, bad))} is not one of them.")
    return idx


def _marker(target, ep):
    return tuple(float(v) for v in ep["wcs"].world_to_pixel(at_time(target, Time(ep["mjd"], format="mjd"))))


def _pick(eps, visit):
    try:
        return eps[visit]
    except IndexError:
        raise ValueError(f"There are only {len(eps)} pictures (use 0..{len(eps) - 1}, or -1 for the latest).")


def _image_figure(img, wcs, title, marker=None, diverging=False, rgb=False):
    fig = plt.figure(figsize=(6.2, 6.4))
    ax = fig.add_subplot(projection=wcs)
    if rgb:
        ax.imshow(img, origin="lower")
    elif diverging:
        lim = np.nanpercentile(np.abs(img), 99.5) or 1
        ax.imshow(img, origin="lower", cmap="RdBu_r", vmin=-lim, vmax=lim)
    else:
        ax.imshow(img, origin="lower", cmap="gray", norm=shared_norm([img]))
    if marker is not None:
        ax.scatter([marker[0]], [marker[1]], s=450, facecolors="none",
                   edgecolors="white" if rgb else "lime", lw=1.2)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("RA"); ax.set_ylabel("Dec")
    return fig, ax


# ------------------------------------------------------------------ 1. search box
def resolve(text):
    """Target text -> dict: name, ra, dec (degrees, catalogue position), ra_hms, dec_dms,
    has_motion, pm_ra, pm_dec (mas/yr), known (True for the five challenge targets)."""
    try:
        c = parse_target(text)
    except ValueError:
        raise ValueError(f"Could not find '{text}'. Check the spelling, or enter coordinates.")
    hms, dms = SkyCoord(c.ra, c.dec).to_string("hmsdms", precision=1).split()
    return {"name": text.strip(), "ra": float(c.ra.deg), "dec": float(c.dec.deg),
            "ra_hms": hms, "dec_dms": dms, "has_motion": has_pm(c),
            "pm_ra": float(c.pm_ra_cosdec.to_value(u.mas / u.yr)) if has_pm(c) else 0.0,
            "pm_dec": float(c.pm_dec.to_value(u.mas / u.yr)) if has_pm(c) else 0.0,
            "known": known_target(text) is not None or known_near(c) is not None}


def visits(text, refresh=False, detector=None, fov=4.0, clip=True):
    """Table with one row per SPHEREx visit: visit, first_date, last_date, n_frames, D1..D6
    (frames per detector), releases. refresh=True searches IRSA again for new data.
    detector='D2' (etc.) adds, from that detector's stacks: n_min (fewest frames under the
    picture's centre; below 4 the picture is unreliable) and clipped_fraction (share of pixel
    values the sigma clipping rejected). This stacks the visits if they are not stacked yet."""
    _, frames = _load(text, refresh=refresh)
    stacks = {}
    if detector:
        stacks = {e["epoch"]: e for e in _epochs(text, detector, fov, clip=clip)[2]}
    rows = []
    for e in sorted(set(frames["epoch"])):
        f = frames[frames["epoch"] == e]
        row = {"visit": int(e), "first_date": f["date"][0][:10], "last_date": f["date"][-1][:10],
               "n_frames": len(f)}
        row.update({f"D{d}": int((f["detector"] == f"D{d}").sum()) for d in range(1, 7)})
        row["releases"] = ", ".join(sorted(set(str(c).replace("spherex_", "") for c in f["collection"])))
        if detector:
            e2 = stacks.get(int(e))
            row["n_min"] = int(e2["n_min"]) if e2 else 0
            row["clipped_fraction"] = round(float(e2["clipped_fraction"]), 5) if e2 else float("nan")
        rows.append(row)
    return Table(rows)


def epochs(text, detector=None, fov=4.0, wl=None, days=60, clip=True, pictures=None):
    """The pictures the other functions build for exactly these settings -> table, one row per
    picture, in their order: row i is picture(..., visit=i), the a / b of kind "pair", and frame i
    of flipbook and player_html (same arguments). Build visit pickers from this, not from visits().
    Columns: index, visit (the visits() number most of its frames belong to), date (as in the
    picture titles), first_date, last_date (of the frames used), n_frames, n_min, clipped_fraction,
    few_frames (fewer than 4 frames under the centre: "few frames: unreliable"), detectors_used,
    releases. Same stacks and memory cache as the pictures: free once a video has been built.
    detector=None means D2, unless wl is given (then the detectors covering wl).
    pictures: optional list of row numbers (index) of the full table; only those rows are returned,
    in time order, and row k is then frame k of flipbook / player_html given the same pictures.
    index stays the number in the full table (what picture(visit=...) and pictures= take)."""
    _, _, eps = _epochs(text, detector, fov, wl, days, clip)
    iso = lambda m: Time(m, format="mjd").iso[:10]
    return Table(rows=[(i, int(e["visit"]), e["date"], iso(e["first_mjd"]), iso(e["last_mjd"]), int(e["n_frames"]),
                        int(e["n_min"]), round(float(e["clipped_fraction"]), 5), bool(_few(e)),
                        e["detectors_used"], e["releases"]) for i, e in ((i, eps[i]) for i in _choose(eps, pictures))],
                 names=["index", "visit", "date", "first_date", "last_date", "n_frames", "n_min",
                        "clipped_fraction", "few_frames", "detectors_used", "releases"])


# ------------------------------------------------------------------ 2. the video
def flipbook(text, detector="D2", fov=4.0, mode="normal", fps=3, wl=None, days=60, timeline=True, clip=True,
             pictures=None):
    """The little video -> GIF as bytes (st.image(gif_bytes)).
    mode: 'normal'     one picture per visit
          'difference' each visit minus the first (movers walk away from a blue hole)
          'minusmean'  each visit minus the average of the others (only changes remain)
    detector: 'D1'..'D6', combinations like 'D5+D6', or 'all'.   fov: width in arcmin.
    wl: optional wavelength range like '4.4-4.7' (micron); detector may then be None.
    days: longest time one picture may cover (60 = one per visit; 7 = weekly pictures).
    clip: True = sigma-clipped stacks (default); False = plain average of the frames, which keeps
    sources seen in only a few frames (fast movers, flares) but also single-frame defects.
    pictures: optional list of row numbers of epochs(...) with the same settings: only those
    pictures are shown, in time order. 'difference' subtracts the first chosen one; 'minusmean'
    uses only the chosen ones. A difference mode needs at least 2."""
    target, eps, titles, norm, cmap = _video_frames(text, detector, fov, mode, wl, days, clip, pictures)
    fd, path = tempfile.mkstemp(suffix=".gif")
    os.close(fd)
    try:
        make_gif([e["image"] for e in eps], titles, path, fps=fps, norm=norm, cmap=cmap,
                 markers=[_marker(target, e) for e in eps],
                 mjds=[e["mjd"] for e in eps] if timeline else None)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.remove(path)


def _video_frames(text, detector, fov, mode, wl, days, clip=True, pictures=None):
    """The pictures of the video -> (target, epochs, titles, norm, cmap)."""
    target, _, eps = _epochs(text, detector, fov, wl, days, clip)
    eps = [eps[i] for i in _choose(eps, pictures)]
    label = eps[0]["detector"]
    norm, cmap = None, "gray"
    if mode in ("difference", "minusmean"):
        if len(eps) < 2:
            raise ValueError("A difference video needs at least 2 pictures. "
                             + ("Choose two or more." if pictures is not None else
                                "These settings give only one."))
        ref = eps[0]
        eps = difference_series(eps) if mode == "difference" else minus_mean(eps)
        vals = np.concatenate([e["image"][np.isfinite(e["image"])] for e in eps])
        lim = np.nanpercentile(np.abs(vals), 99.5) or 1
        norm, cmap = Normalize(-lim, lim), "RdBu_r"
        # a difference is as unreliable as either picture in it
        titles = [_with_few(f"{text}  {label}  {e['label']}", *((e, ref) if mode == "difference" else (e,)))
                  for e in eps]
        for e in eps:
            e["few"] = _few(*((e, ref) if mode == "difference" else (e,)))
    elif mode == "normal":
        titles = [_with_few(f"{text}  {label}  {e['date']}  ({e['n_frames']} frames)", e) for e in eps]
        eps = [dict(e, few=_few(e)) for e in eps]
    else:
        raise ValueError("mode must be 'normal', 'difference' or 'minusmean'.")
    return target, eps, titles, norm or shared_norm([e["image"] for e in eps]), cmap


def player_html(text, detector="D2", fov=4.0, mode="normal", fps=3, wl=None, days=60, width=700, clip=True,
                pictures=None):
    """The video as a small web page with play/pause, step and a slider -> HTML string
    (streamlit.components.v1.html(html, height=...)). Same pictures as flipbook(), including pictures=."""
    import base64
    import html as _html
    import io
    import json
    target, eps, titles, norm, cmap = _video_frames(text, detector, fov, mode, wl, days, clip, pictures)
    pngs = []
    fig, ax = plt.subplots(figsize=(6, 6))
    for e, title in zip(eps, titles):
        ax.clear()
        ax.imshow(e["image"], origin="lower", cmap=cmap, norm=norm)
        x, y = _marker(target, e)
        ax.scatter([x], [y], s=400, facecolors="none", edgecolors="lime", lw=1.2)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title, fontsize=10)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
        pngs.append("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode())
    plt.close(fig)
    labels = [_html.escape((e.get("label") or e.get("date", "")) + (f"  ({e['few']})" if e.get("few") else ""))
              for e in eps]
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body {{ margin:0; background:#1a1a19; color:#f0efec; font:13px system-ui, sans-serif; }}
img {{ width:100%; max-width:{int(width)}px; display:block; margin:0 auto; }}
.bar {{ display:flex; gap:8px; align-items:center; justify-content:center; margin:8px 0; }}
button {{ background:transparent; color:#f0efec; border:1px solid #383835; border-radius:2px; padding:3px 10px; cursor:pointer; }}
input[type=range] {{ flex:1; max-width:420px; }}
</style></head><body>
<img id="f" alt="SPHEREx video frame">
<div class="bar"><button id="prev">&#9664;</button><button id="play">pause</button><button id="next">&#9654;</button>
<input id="s" type="range" min="0" max="{len(pngs) - 1}" value="0"><span id="d"></span></div>
<script>
const F = {json.dumps(pngs)}, L = {json.dumps(labels)};
let i = 0, timer = null;
const img = document.getElementById("f"), s = document.getElementById("s"), d = document.getElementById("d"),
      play = document.getElementById("play");
function show(k) {{ i = (k + F.length) % F.length; img.src = F[i]; s.value = i;
                    d.textContent = (i + 1) + "/" + F.length + "  " + L[i]; }}
function start() {{ timer = setInterval(() => show(i + 1), {int(1000 / max(fps, 1))}); play.textContent = "pause"; }}
function stop() {{ clearInterval(timer); timer = null; play.textContent = "play"; }}
play.onclick = () => timer ? stop() : start();
document.getElementById("prev").onclick = () => {{ stop(); show(i - 1); }};
document.getElementById("next").onclick = () => {{ stop(); show(i + 1); }};
s.oninput = () => {{ stop(); show(+s.value); }};
show(0); if (F.length > 1) start(); else play.disabled = true;
</script></body></html>"""


# ------------------------------------------------------------------ 3. single pictures
def picture(text, kind="visit", detector="D2", fov=4.0, visit=-1, a=-1, b=0, wl=None,
            long="D6", short="D2", rgb="D6,D3,D1", clip=True, days=60):
    """One picture -> matplotlib figure (st.pyplot(fig)).
    kind: 'visit'    one visit's stack (visit = 0, 1, ... or -1 for the latest)
          'deep'     all visits added
          'pair'     the later of visits a and b minus the earlier (red = brighter later,
                     blue = brighter earlier), whichever order a and b are given in
          'banddiff' detector `long` minus scaled detector `short`, latest common visit:
                     normal stars cancel, unusually red (cold) objects stay
          'rgb'      colour picture from three detectors 'red,green,blue'
    clip: True = sigma-clipped stacks; False = plain average (see flipbook).
    days: as in flipbook; visit, a and b are rows of epochs(..., days=days), the same pictures
    as the video with those settings. banddiff / rgb use the latest picture all detectors share."""
    if kind in ("visit", "deep", "pair"):
        target, _, eps = _epochs(text, detector, fov, wl, days, clip)
        label = eps[0]["detector"]
        if kind == "visit":
            ep = _pick(eps, visit)
            fig, _ = _image_figure(ep["image"], ep["wcs"], _with_few(f"{text}  {label}  {ep['date']}  "
                                   f"({ep['n_frames']} frames)", ep), _marker(target, ep))
        elif kind == "deep":
            ep = deep_image(eps)
            fig, _ = _image_figure(ep["image"], ep["wcs"], _with_few(f"{text}  {label}  {ep['label']}\n"
                                   f"{ep['n_frames']} frames, {ep['date']}", *eps), _marker(target, eps[-1]))
        else:
            if len(eps) < 2:
                raise ValueError("A difference needs at least 2 visits.")
            later, earlier = sorted([_pick(eps, a), _pick(eps, b)], key=lambda e: e["mjd"], reverse=True)
            if later is earlier:
                raise ValueError("A difference needs two different visits.")
            d = difference(later, earlier)
            fig, _ = _image_figure(d["image"], d["wcs"], _with_few(
                f"{text}  {label}  later minus earlier: {d['label']}\n"
                "red = brighter later, blue = brighter earlier", later, earlier),
                _marker(target, d), diverging=True)
        return fig
    if kind in ("banddiff", "rgb"):
        dets = [long, short] if kind == "banddiff" else [x.strip() for x in str(rgb).split(",")]
        if kind == "rgb" and len(dets) != 3:
            raise ValueError("rgb needs three detectors, like 'D6,D3,D1'.")
        sets = []
        for d in dets:
            target, _, eps = _epochs(text, d, fov, None, days, clip)
            sets.append(eps)
        common = sorted(set.intersection(*[set(e["epoch"] for e in s) for s in sets]))
        if not common:
            raise ValueError(f"No visit has images in all of {', '.join(dets)}.")
        chosen = [[x for x in s if x["epoch"] == common[-1]][0] for s in sets]
        if kind == "banddiff":
            d = band_difference(chosen[0], chosen[1])
            fig, _ = _image_figure(d["image"], d["wcs"], _with_few(f"{text}  {d['label']}\n"
                                   f"red = brighter in {dets[0]}, blue = brighter in scaled {dets[1]} "
                                   "(normal stars cancel)", *chosen),
                                   _marker(target, d), diverging=True)
        else:
            img = rgb_image(*[c["image"] for c in chosen])
            fig, _ = _image_figure(img, chosen[0]["wcs"], _with_few(f"{text}  {chosen[0]['date']}\n"
                                   f"red = {dets[0]}, green = {dets[1]}, blue = {dets[2]}", *chosen),
                                   _marker(target, chosen[0]), rgb=True)
        return fig
    raise ValueError("kind must be 'visit', 'deep', 'pair', 'banddiff' or 'rgb'.")


# ------------------------------------------------------------------ 4. overlays
HALO_G = 10.0              # Gaia stars brighter than this that CatWISE lacks are saturated in WISE
HALO_ARCSEC = 150.0        # ... and around them CatWISE lists fake "significant" motions


def _distrust_halo_motions(wise_stars, center, radius, t):
    """Set pm_snr = 0 (no arrow) for WISE sources within HALO_ARCSEC of a Gaia star brighter
    than HALO_G that has no CatWISE counterpart within 3": such a star is saturated in WISE,
    and its halo is full of spurious sources with large motions (89 at >= 5 sigma around
    Barnard's Star). Returns how many bright halo stars were found (0 if Gaia is unavailable)."""
    if not len(wise_stars) or "pm_snr" not in wise_stars.colnames:
        return 0
    try:
        gaia = gaia_overlay(center, radius, t)
    except Exception:
        return 0
    bright = gaia[np.nan_to_num(np.asarray(gaia["phot_g_mean_mag"], float), nan=99) < HALO_G]
    if not len(bright):
        return 0
    w = SkyCoord(wise_stars["ra_t"] * u.deg, wise_stars["dec_t"] * u.deg)
    n = 0
    for star in bright:
        s = SkyCoord(star["ra_t"] * u.deg, star["dec_t"] * u.deg)
        sep = w.separation(s).arcsec
        if (sep < 3).any():
            continue                                   # CatWISE measured it: not saturated
        wise_stars["pm_snr"][sep < HALO_ARCSEC] = 0.0
        n += 1
    return n


def overlay_figure(text, detector="D2", fov=4.0, visit=-1, gaia=True, wise=True, asteroids=False,
                   min_pm=50, arrow_years=5, days=60):
    """A visit's picture with catalogue overlays -> (figure, notes).
    notes is a dict: what was drawn, what failed, and a catalogue check for the target
    ('in_gaia', 'in_wise', 'nearest_gaia_arcsec', 'nearest_wise_arcsec', 'verdict').
    The verdict only says which catalogues have a source within 3 arcsec - not whether
    SPHEREx detects anything. WISE motions get an arrow only when measured at >= 5 sigma.
    visit is a row of epochs(text, detector, fov, days=days)."""
    target, _, eps = _epochs(text, detector, fov, None, days)
    ep = _pick(eps, visit)
    t = Time(ep["mjd"], format="mjd")
    shape = ep["image"].shape
    center = ep["wcs"].pixel_to_world(shape[1] / 2, shape[0] / 2)
    radius = 0.15            # covers a 10' view (half-diagonal 0.118 deg); same circle as the demo cache
    now = at_time(target, t)
    fig, ax = _image_figure(ep["image"], ep["wcs"], "", _marker(target, ep))
    notes = {"drawn": [], "failed": []}
    for name, wanted, fn, kw in [
            ("gaia", gaia, gaia_overlay, {}),
            ("wise", wise, wise_overlay, dict(color="#e87ba4", fast_color="#eb6834", marker="s"))]:
        if not wanted:
            continue
        try:
            stars = fn(center, radius, t)
            if name == "wise":
                notes["wise_halo_stars"] = _distrust_halo_motions(stars, center, radius, t)
            draw_gaia(ax, stars, ep["wcs"], shape, min_pm=min_pm, arrow_years=arrow_years, **kw)
            notes["drawn"].append(name)
            if len(stars):
                sep = SkyCoord(stars["ra_t"] * u.deg, stars["dec_t"] * u.deg).separation(now).arcsec
                notes[f"nearest_{name}_arcsec"] = float(sep.min())
                notes[f"in_{name}"] = bool(sep.min() < 3)
            else:
                notes[f"in_{name}"] = False
        except Exception as e:
            notes["failed"].append(f"{name}: {type(e).__name__}")
    if asteroids:
        try:
            notes["asteroids_in_view"] = draw_asteroids(ax, known_asteroids(center, fov / 60 * 0.75, t),
                                                        ep["wcs"], shape)
            notes["drawn"].append("asteroids")
        except Exception as e:
            notes["failed"].append(f"asteroids: {type(e).__name__}")
    if "in_gaia" in notes and "in_wise" in notes:
        where = "the target's predicted position" if has_pm(target) else "this position"
        notes["verdict"] = (
            f"Catalogue check: a Gaia DR3 source lies within 3″ of {where} (a known star)."
            if notes["in_gaia"] else
            f"Catalogue check: a CatWISE2020 source lies within 3″ of {where}, none in Gaia "
            "(a known object that is faint or cold in visible light)." if notes["in_wise"] else
            f"Catalogue check: no Gaia DR3 or CatWISE2020 source within 3″ of {where}. This is "
            "not a detection: look at the pictures to see whether SPHEREx shows anything there. "
            "Very bright stars and fast movers can be missing from these catalogues.")
    ax.set_title(_with_few(f"{text}  {ep['detector']}  {ep['date']}\ncircles = Gaia, squares = WISE, "
                           f"arrows = next {arrow_years:g} years, green = target", ep), fontsize=9)
    notes["n_min"] = ep.get("n_min")
    notes["clipped_fraction"] = ep.get("clipped_fraction")
    notes["few_frames"] = bool(_few(ep))
    return fig, notes


# ------------------------------------------------------------------ 5. measurements
APERTURE_ARCSEC = 2 * 6.15          # measure_frame's r_px=2 on 6.15" SPHEREx pixels
SELF_MATCH_ARCSEC = 2.0             # a Gaia source this close to the target is the target itself
CLOSE_NEIGHBOUR_ARCSEC = 8.0        # a neighbour this close dominates where the target is faint


def _neighbour_warning(target, mjd):
    """Gaia stars inside the measuring circle around the target on date `mjd` -> warning text,
    or None. Their light is added to the target's, most at short wavelengths. A catalogue that
    cannot be reached gives no warning (the measurement is still shown)."""
    t = Time(float(mjd), format="mjd")
    pos = at_time(target, t)
    try:
        # 0.05 deg: the cone selects on Gaia's 2016 positions, and the target itself may have
        # moved far since (Barnard's Star: 110" by 2026). Too small a cone loses the target's
        # own entry, and with it the brightness test below.
        stars = gaia_overlay(pos, 0.05, t)
    except Exception:
        return None
    if not len(stars):
        return None
    sep = SkyCoord(stars["ra_t"] * u.deg, stars["dec_t"] * u.deg).separation(pos).arcsec
    g = np.asarray(stars["phot_g_mean_mag"], float)
    near = (sep > SELF_MATCH_ARCSEC) & (sep < APERTURE_ARCSEC)
    own = g[(sep <= SELF_MATCH_ARCSEC) & np.isfinite(g)]
    if len(own):                     # target in Gaia: only neighbours worth >= 10% of its light count
        near &= g < own.min() + 2.5
    if not near.any():
        return None
    mags = g[near]
    parts = [f"G={g:.1f} at {d:.1f}″" for d, g in sorted(zip(sep[near], mags))]
    text = (f"{int(near.sum())} Gaia star(s) inside the {APERTURE_ARCSEC:.0f}″ measuring circle "
            f"({', '.join(parts)}): part of the light measured comes from them, mostly at short "
            "wavelengths. Treat these brightnesses as upper limits.")
    close = near & (sep < CLOSE_NEIGHBOUR_ARCSEC)
    if close.any():
        i = np.flatnonzero(close)[np.argmin(sep[close])]
        text += (f" The neighbour at {sep[i]:.1f}″ (G={g[i]:.1f}) is so close that, at wavelengths where "
                 "the target is faint, the measured light is "
                 "mostly this neighbour, not the target.")
    return text


SATURATED_NOTE = ("The target is saturated (too bright for SPHEREx) here: triangles are lower limits from the unsaturated wings of the star; its true brightness is higher.")


def _mixed_releases_note(table):
    """Warning text when the measurements come from more than one data release, else None."""
    rel = sorted(set(str(r) for r in table["release"] if str(r))) if "release" in table.colnames else []
    if len(rel) < 2:
        return None
    return (f"These measurements come from different data releases ({', '.join(rel)}). Their calibration "
            "can differ by several percent, so a step between releases is not necessarily a real change.")


def _wavelength_spread_note(lc):
    """Warning text when the usable light-curve points differ in wavelength by more than WL_SPREAD_UM."""
    spread = wavelength_spread(lc)
    if spread <= WL_SPREAD_UM:
        return None
    wl = np.asarray(lc["wavelength_um"][lc["ok"]], float)
    return (f"The usable points were measured at slightly different wavelengths ({wl.min():.3f} to "
            f"{wl.max():.3f} µm). On a steep spectrum that alone can change the flux by several percent, "
            "so differences of that size are not necessarily a change of the source.")


def _join(*notes):
    return " ".join(n for n in notes if n) or None


def _state(t):
    """Per-row state and 'masked' flag of a measurement table (light curve or spectrum):
    ok        usable, drawn as a point;
    saturated star saturated: flux_mjy is NaN, flux_min_mjy (if finite) is a lower limit;
    masked    most of the measuring circle masked: not measured, no value at all;
    flagged   a value exists but some masked pixels are in the circle: not used."""
    ok = np.asarray(t["ok"], bool)
    sat = np.asarray(t["saturated"], bool)
    nan = ~np.isfinite(np.asarray(t["flux_mjy"], float))
    masked = nan & ~sat & ~ok
    t["masked"] = masked
    t["state"] = np.where(ok, "ok", np.where(sat, "saturated", np.where(masked, "masked", "flagged")))
    return t


def _light_curve_table(lc):
    """Light-curve rows + what the figure draws per visit: visit_mjd (where the visit average is
    drawn), visit_flux_mjy (mean of the visit's usable points), visit_spread_mjy (their standard
    deviation; the point's own error if there is only one), visit_n_ok (usable points; 1 = drawn as
    an open 'single measurement' symbol, not joined by a line). NaN / 0 for visits with none."""
    lc = _state(lc)
    v = np.asarray(lc["visit"])
    ok = np.asarray(lc["ok"], bool)
    flux, err = np.asarray(lc["flux_mjy"], float), np.asarray(lc["err_mjy"], float)
    cols = {k: np.full(len(lc), np.nan) for k in ("visit_mjd", "visit_flux_mjy", "visit_spread_mjy")}
    n_ok = np.zeros(len(lc), int)
    for x in set(v):
        rows, good = v == x, (v == x) & ok
        cols["visit_mjd"][rows] = np.mean(np.asarray(lc["mjd"], float)[rows])
        n_ok[rows] = good.sum()
        if good.any():
            cols["visit_flux_mjy"][rows] = flux[good].mean()
            cols["visit_spread_mjy"][rows] = flux[good].std() if good.sum() > 1 else err[good][0]
    for k, val in cols.items():
        lc[k] = val
    lc["visit_n_ok"] = n_ok
    return lc


def _spectrum_table(spec, binned, visit):
    """One row per measurement of a spectrum (as plot_spectrum draws them), with state/masked, the
    visit, and the channel average the row falls in: channel (1-17, 0 = outside the channel grid),
    channel_wavelength_um (channel centre, where the average is drawn), channel_flux_mjy,
    channel_err_mjy, channel_n. The channel columns are NaN / 0 where no average is drawn
    (no usable measurement in that channel, or a saturated visit shown as lower limits only)."""
    t = _state(spec.copy())
    t["visit"] = np.full(len(t), int(visit))
    edges = channel_edges()
    det, wl = np.asarray(t["detector"], int), np.asarray(t["wavelength_um"], float)
    ch = np.zeros(len(t), int)
    for i, (d, w) in enumerate(zip(det, wl)):
        e = edges.get(d)
        if e is not None and e[0] <= w < e[-1]:
            ch[i] = int(np.searchsorted(e, w, side="right"))
    t["channel"] = ch
    avg = {(int(r["detector"]), int(r["channel"])): r for r in binned}
    for col, src in [("channel_wavelength_um", "wavelength_um"), ("channel_flux_mjy", "flux_mjy"),
                     ("channel_err_mjy", "err_mjy")]:
        t[col] = [float(avg[(d, c)][src]) if (d, c) in avg else np.nan for d, c in zip(det, ch)]
    t["channel_n"] = [int(avg[(d, c)]["n"]) if (d, c) in avg else 0 for d, c in zip(det, ch)]
    return t


def _with_warning(fig, table, warning):
    """Put a neighbour warning on the figure (bottom line) and in table.meta['warning']."""
    if warning:
        table.meta["warning"] = warning
        fig.subplots_adjust(bottom=max(fig.subplotpars.bottom, 0.22))
        fig.text(0.01, 0.01, "⚠ " + warning, fontsize=7, color="#eda100", ha="left", va="bottom", wrap=True)
    return fig, table


def light_curve_figure(text, band=1.6, tol=0.02):
    """Brightness over time at one wavelength (micron) -> (figure, table).
    Table columns: mjd, date, wavelength_um, flux_mjy, err_mjy, flux_min_mjy, detector, n_bad, saturated,
    bad_flags, ok, release, visit, masked, state, visit_mjd, visit_flux_mjy, visit_spread_mjy,
    visit_n_ok (see _light_curve_table). table.meta['warning'] (if present) explains saturation, neighbours in the
    measuring circle, a wavelength spread above WL_SPREAD_UM between the usable points, a mix of
    data releases, or a tolerance above MAX_SAFE_TOL.
    Keep tol small: a wide window mixes wavelengths, which can look like variability.
    The time axis covers all visits of the target, not only the measured ones."""
    target, frames = _load(text)
    lc = light_curve(frames, target, band, tol_um=tol)
    if len(lc) == 0:
        raise ValueError(f"No image has '{text}' at {band:g} ± {tol:g} micron. Try another wavelength: "
                         "the visits table shows which detectors observed this target."
                         + (" Demo mode uses only images already in cache/." if net.DEMO_MODE else ""))
    fig = plot_light_curve_simple(lc, f"{text}: brightness at {band:g} ± {tol:g} µm",
                                  span_mjd=(frames["mjd"].min(), frames["mjd"].max()))
    lc = _light_curve_table(lc)
    warning = SATURATED_NOTE if (lc["saturated"] & ~lc["ok"]).any() else None
    wide = (f"The tolerance of ±{tol:g} µm mixes wavelengths; across a steep spectrum that alone can look "
            f"like variability. Use ±{MAX_SAFE_TOL:g} µm or less to compare brightnesses.") if tol > MAX_SAFE_TOL else None
    return _with_warning(fig, lc, _join(warning, wide, _wavelength_spread_note(lc), _mixed_releases_note(lc),
                                        _neighbour_warning(target, np.median(lc["mjd"]))))


def spectrum_figure(text, visit=-1, all_visits=False):
    """Brightness at every wavelength -> (figure, table).
    visit: which visit (-1 = latest). all_visits=True overlays every visit instead.
    The table has one row per measurement, everything the figure draws: wavelength_um, flux_mjy,
    err_mjy, flux_min_mjy, detector, mjd, n_bad, saturated, bad_flags, ok, release, masked, state,
    visit, channel, channel_wavelength_um, channel_flux_mjy, channel_err_mjy, channel_n
    (see _spectrum_table)."""
    target, frames = _load(text)
    ids = sorted(set(frames["epoch"]))
    if all_visits:
        per, tables, specs, saturated = [], [], [], False
        for e in ids:
            sub = frames[frames["epoch"] == e]
            spec = spectrum(sub, target)
            b = bin_to_channels(spec)
            if len(spec) and spec["saturated"].mean() > 0.5 and len(b) < 5:
                b = b[:0]                                  # a few stray channels: show the limits instead
                saturated = True
            per.append((sub["date"][0][:10], b, spec))
            if len(spec):
                specs.append(_spectrum_table(spec, b, e))
        if not specs:
            raise ValueError(f"No spectrum could be measured for '{text}' in any visit.")
        from astropy.table import vstack
        table = vstack(specs)
        mixed = _mixed_releases_note(vstack(specs))
        fig = plot_spectra_visits(per, f"{text}: spectrum of every visit")
        if mixed:
            rel = sorted(set(str(r) for r in vstack(specs)["release"] if str(r)))
            fig.axes[0].text(1.01, 0.0, f"mixed data releases ({', '.join(rel)}):\n"
                             "calibration may differ between them", transform=fig.axes[0].transAxes,
                             ha="left", va="bottom", fontsize=8, color=THEME["flag"])   # under the legend
        return _with_warning(fig, table, _join(SATURATED_NOTE if saturated else None, mixed,
                                               _neighbour_warning(target, np.median(frames["mjd"]))))
    try:
        sub = frames[frames["epoch"] == ids[visit]]
    except IndexError:
        raise ValueError(f"There are only {len(ids)} visits.")
    spec = spectrum(sub, target)
    binned = bin_to_channels(spec)
    if len(spec) == 0:
        raise ValueError(f"No spectrum could be measured for '{text}' in that visit.")
    saturated = spec["saturated"].mean() > 0.5 and len(binned) < 5
    if saturated:
        binned = binned[:0]                                # a few stray channels: show the limits instead
    fig = plot_spectrum(spec, binned, f"{text}: spectrum, visit of {sub['date'][0][:10]}", log="auto")
    table = _spectrum_table(spec, binned, ids[visit])
    return _with_warning(fig, table, _join(SATURATED_NOTE if saturated else None,
                                           _neighbour_warning(target, np.median(sub["mjd"]))))


# ------------------------------------------------------------------ 6. contamination flags
def flags_figure(text, detector="D2", visit=-1, frame=0):
    """One single exposure with its flagged pixels -> (figure, table).
    Left: the raw image. Right: cleaned image with masked pixels in red.
    Table: every flag with the percentage of pixels that carry it, and whether we mask it.
    visit counts only visits with images from this detector (-1 = the latest such visit).
    If exposure `frame` cannot be loaded (demo mode, not in cache/), the next one that can is shown."""
    target, frames = _load(text)
    det = parse_detectors(detector)[0]
    mine = frames[frames["detector"] == det]
    ids = sorted(set(mine["epoch"]))
    if not ids:
        raise ValueError(f"There are no {det} images of '{text}'.")
    try:
        rows = mine[mine["epoch"] == ids[visit]]
    except IndexError:
        raise ValueError(f"There are only {len(ids)} visits with {det} images.")
    if not 0 <= frame < len(rows):
        raise ValueError(f"That visit has {len(rows)} {det} exposures (use 0..{len(rows) - 1}).")
    for row in list(rows[frame:]) + list(rows[:frame]):
        pos = at_time(target, Time(row["mjd"], format="mjd"))
        try:
            path = get_cutout(row["access_url"], pos, 0.1)
            break
        except OSError:
            continue
    else:
        raise ValueError(f"None of the {det} exposures of that visit is available offline.")
    f = clean_frame(path)
    cmap = plt.get_cmap("gray").copy()
    cmap.set_bad("red")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4))
    for ax, key, title in [(axes[0], "raw", "as observed"), (axes[1], "image", "cleaned: red = masked pixels")]:
        ax.imshow(f[key], origin="lower", cmap=cmap, norm=shared_norm([f[key]]))
        x, y = f["wcs"].world_to_pixel(pos)
        ax.scatter([x], [y], s=350, facecolors="none", edgecolors="lime", lw=1)
        ax.set_title(title, fontsize=10); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"{text}  {det}  {row['date'][:16]}  ({str(row['collection']).replace('spherex_', '')})",
                 x=0.02, ha="left", fontweight="bold")
    table = Table(rows=[(n.removeprefix("MP_"), b, round(float(((f["flags"] & (1 << b)) != 0).mean() * 100), 2),
                         n in BAD_FLAGS) for n, b in sorted(f["bits"].items(), key=lambda kv: kv[1])],
                  names=["flag", "bit", "percent_of_pixels", "masked"])
    return fig, table[table["percent_of_pixels"] > 0]
