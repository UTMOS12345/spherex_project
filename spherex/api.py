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
from .epochs import assign_epochs, make_epochs, parse_detectors
from .frames import load_or_find_frames
from .gaia import gaia_overlay, draw_gaia
from .photometry import light_curve
from .plots import plot_light_curve_simple, plot_spectrum, plot_spectra_visits
from .spectrum import spectrum, bin_to_channels
from .targets import parse_target, at_time, has_pm, known_target, target_name
from .wise import wise_overlay
from . import net
from .net import set_demo_mode            # api.set_demo_mode(True): cached data only, no hangs

MAX_FOV = 10.0            # arcmin served from the standard downloads
_memory = {}              # stacks already made in this process: key -> list of epochs

# Settings whose images prepare_demo.py downloads for the challenge targets: with these the
# app runs from cache/ without downloads. prepare_demo.py reads this table too.
DEMO_DEFAULTS = {
    "Barnard's Star": dict(detector="D2", band=1.3, tol=0.05),   # moves fast; saturated -> no fluxes
    "WISE 0855":      dict(detector="D6", band=4.5, tol=0.10),   # cold brown dwarf: only seen at 4-5 um
    "Epsilon Indi B": dict(detector="D5", band=4.2, tol=0.10),   # brown dwarf pair, fast mover
    "RW Aur":         dict(detector="D1", band=0.9, tol=0.05),   # variable; saturates at 1.6 um
    "R Draconis":     dict(detector="D3", band=2.2, tol=0.10),   # pulsating red giant; saturated
}
OTHER_DEFAULTS = dict(detector="D2", band=1.6, tol=0.05)


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


def _epochs(text, detector="D2", fov=4.0, wl=None, days=60):
    """Stacked visits (memory-cached). detector may be None when wl is given."""
    if not 1 <= fov <= 30:
        raise ValueError("Field of view must be between 1 and 30 arcmin.")
    wl = _wl(wl)
    det = None if (wl and not detector) else "+".join(parse_detectors(detector or "D2"))
    target, frames = _load(text)
    # the frame URLs are part of the key: a refresh that swaps releases rebuilds the stacks
    key = (target_name(text, target), det, round(float(fov), 2), wl, days, hash(tuple(frames["access_url"])))
    if key not in _memory:
        eps = make_epochs(frames, target, det, grid_arcmin=fov, wl_range=wl,
                          gap_days=min(30, days), max_len_days=days)
        if not eps:
            raise ValueError(f"No usable {det or 'matching'} images of '{text}'"
                             + (f" at {wl[0]}-{wl[1]} micron." if wl else "."))
        if len(_memory) > 40:
            _memory.pop(next(iter(_memory)))
        _memory[key] = eps
    return target, frames, _memory[key]


def _marker(target, ep):
    return tuple(float(v) for v in ep["wcs"].world_to_pixel(at_time(target, Time(ep["mjd"], format="mjd"))))


def _pick(eps, visit):
    try:
        return eps[visit]
    except IndexError:
        raise ValueError(f"There are only {len(eps)} visits (use 0..{len(eps) - 1}, or -1 for the latest).")


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
            "known": known_target(text) is not None}


def visits(text, refresh=False):
    """Table with one row per SPHEREx visit: visit, first_date, last_date, n_frames, D1..D6
    (frames per detector), releases. refresh=True searches IRSA again for new data."""
    _, frames = _load(text, refresh=refresh)
    rows = []
    for e in sorted(set(frames["epoch"])):
        f = frames[frames["epoch"] == e]
        row = {"visit": int(e), "first_date": f["date"][0][:10], "last_date": f["date"][-1][:10],
               "n_frames": len(f)}
        row.update({f"D{d}": int((f["detector"] == f"D{d}").sum()) for d in range(1, 7)})
        row["releases"] = ", ".join(sorted(set(str(c).replace("spherex_", "") for c in f["collection"])))
        rows.append(row)
    return Table(rows)


# ------------------------------------------------------------------ 2. the video
def flipbook(text, detector="D2", fov=4.0, mode="normal", fps=3, wl=None, days=60, timeline=True):
    """The little video -> GIF as bytes (st.image(gif_bytes)).
    mode: 'normal'     one picture per visit
          'difference' each visit minus the first (movers walk away from a blue hole)
          'minusmean'  each visit minus the average of the others (only changes remain)
    detector: 'D1'..'D6', combinations like 'D5+D6', or 'all'.   fov: width in arcmin.
    wl: optional wavelength range like '4.4-4.7' (micron); detector may then be None.
    days: longest time one picture may cover (60 = one per visit; 7 = weekly pictures)."""
    target, _, eps = _epochs(text, detector, fov, wl, days)
    label = eps[0]["detector"]
    norm, cmap = None, "gray"
    if mode in ("difference", "minusmean"):
        if len(eps) < 2:
            raise ValueError("A difference video needs at least 2 visits.")
        eps = difference_series(eps) if mode == "difference" else minus_mean(eps)
        vals = np.concatenate([e["image"][np.isfinite(e["image"])] for e in eps])
        lim = np.nanpercentile(np.abs(vals), 99.5) or 1
        norm, cmap = Normalize(-lim, lim), "RdBu_r"
        titles = [f"{text}  {label}  {e['label']}" for e in eps]
    elif mode == "normal":
        titles = [f"{text}  {label}  {e['date']}  ({e['n_frames']} frames)" for e in eps]
    else:
        raise ValueError("mode must be 'normal', 'difference' or 'minusmean'.")
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


# ------------------------------------------------------------------ 3. single pictures
def picture(text, kind="visit", detector="D2", fov=4.0, visit=-1, a=-1, b=0, wl=None,
            long="D6", short="D2", rgb="D6,D3,D1"):
    """One picture -> matplotlib figure (st.pyplot(fig)).
    kind: 'visit'    one visit's stack (visit = 0, 1, ... or -1 for the latest)
          'deep'     all visits added
          'pair'     visit a minus visit b (red = brighter in a, blue = brighter in b)
          'banddiff' detector `long` minus scaled detector `short`, latest common visit:
                     normal stars cancel, unusually red (cold) objects stay
          'rgb'      colour picture from three detectors 'red,green,blue'"""
    if kind in ("visit", "deep", "pair"):
        target, _, eps = _epochs(text, detector, fov, wl)
        label = eps[0]["detector"]
        if kind == "visit":
            ep = _pick(eps, visit)
            fig, _ = _image_figure(ep["image"], ep["wcs"], f"{text}  {label}  {ep['date']}  "
                                   f"({ep['n_frames']} frames)", _marker(target, ep))
        elif kind == "deep":
            ep = deep_image(eps)
            fig, _ = _image_figure(ep["image"], ep["wcs"], f"{text}  {label}  {ep['label']}\n"
                                   f"{ep['n_frames']} frames, {ep['date']}", _marker(target, eps[-1]))
        else:
            if len(eps) < 2:
                raise ValueError("A difference needs at least 2 visits.")
            d = difference(_pick(eps, a), _pick(eps, b))
            fig, _ = _image_figure(d["image"], d["wcs"], f"{text}  {label}  {d['label']}\n"
                                   "red = brighter in the first date, blue = in the second",
                                   _marker(target, d), diverging=True)
        return fig
    if kind in ("banddiff", "rgb"):
        dets = [long, short] if kind == "banddiff" else [x.strip() for x in str(rgb).split(",")]
        if kind == "rgb" and len(dets) != 3:
            raise ValueError("rgb needs three detectors, like 'D6,D3,D1'.")
        sets = []
        for d in dets:
            target, _, eps = _epochs(text, d, fov)
            sets.append(eps)
        common = sorted(set.intersection(*[set(e["epoch"] for e in s) for s in sets]))
        if not common:
            raise ValueError(f"No visit has images in all of {', '.join(dets)}.")
        chosen = [[x for x in s if x["epoch"] == common[-1]][0] for s in sets]
        if kind == "banddiff":
            d = band_difference(chosen[0], chosen[1])
            fig, _ = _image_figure(d["image"], d["wcs"], f"{text}  {d['label']}\n"
                                   "red = brighter at long wavelengths than normal stars",
                                   _marker(target, d), diverging=True)
        else:
            img = rgb_image(*[c["image"] for c in chosen])
            fig, _ = _image_figure(img, chosen[0]["wcs"], f"{text}  {chosen[0]['date']}\n"
                                   f"red = {dets[0]}, green = {dets[1]}, blue = {dets[2]}",
                                   _marker(target, chosen[0]), rgb=True)
        return fig
    raise ValueError("kind must be 'visit', 'deep', 'pair', 'banddiff' or 'rgb'.")


# ------------------------------------------------------------------ 4. overlays
def overlay_figure(text, detector="D2", fov=4.0, visit=-1, gaia=True, wise=True, asteroids=False,
                   min_pm=50, arrow_years=5):
    """A visit's picture with catalogue overlays -> (figure, notes).
    notes is a dict: what was drawn, what failed, and the verdict for the target
    ('in_gaia', 'in_wise', 'nearest_gaia_arcsec', 'nearest_wise_arcsec', 'verdict')."""
    target, _, eps = _epochs(text, detector, fov)
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
        notes["verdict"] = ("known star (in Gaia)" if notes["in_gaia"] else
                            "known cold or faint object (in WISE, not in Gaia)" if notes["in_wise"] else
                            "not in Gaia or WISE at this position: worth a closer look")
    ax.set_title(f"{text}  {ep['detector']}  {ep['date']}\ncircles = Gaia, squares = WISE, "
                 f"arrows = next {arrow_years:g} years, green = target", fontsize=9)
    return fig, notes


# ------------------------------------------------------------------ 5. measurements
def light_curve_figure(text, band=1.6, tol=0.05):
    """Brightness over time at one wavelength (micron) -> (figure, table).
    Table columns: date, wavelength_um, flux_mjy, err_mjy, detector, n_bad, saturated, bad_flags, ok."""
    target, frames = _load(text)
    lc = light_curve(frames, target, band, tol_um=tol)
    if len(lc) == 0:
        raise ValueError(f"No image has '{text}' at {band} ± {tol} micron. Try a wider tolerance.")
    return plot_light_curve_simple(lc, f"{text}: brightness at {band:g} ± {tol:g} µm"), lc


def spectrum_figure(text, visit=-1, all_visits=False):
    """Brightness at every wavelength -> (figure, table of channel averages).
    visit: which visit (-1 = latest). all_visits=True overlays every visit instead
    (the table then has an extra 'visit' column)."""
    target, frames = _load(text)
    ids = sorted(set(frames["epoch"]))
    if all_visits:
        per, tables = [], []
        for e in ids:
            sub = frames[frames["epoch"] == e]
            b = bin_to_channels(spectrum(sub, target))
            per.append((sub["date"][0][:10], b))
            if len(b):
                b = b.copy(); b["visit"] = int(e); tables.append(b)
        if not tables:
            raise ValueError(f"No usable spectrum for '{text}' (saturated or too faint).")
        from astropy.table import vstack
        return plot_spectra_visits(per, f"{text}: spectrum of every visit"), vstack(tables)
    try:
        sub = frames[frames["epoch"] == ids[visit]]
    except IndexError:
        raise ValueError(f"There are only {len(ids)} visits.")
    spec = spectrum(sub, target)
    binned = bin_to_channels(spec)
    if len(spec) == 0:
        raise ValueError(f"No spectrum could be measured for '{text}' in that visit.")
    fig = plot_spectrum(spec, binned, f"{text}: spectrum, visit of {sub['date'][0][:10]}", log="auto")
    return fig, binned


# ------------------------------------------------------------------ 6. contamination flags
def flags_figure(text, detector="D2", visit=-1, frame=0):
    """One single exposure with its flagged pixels -> (figure, table).
    Left: the raw image. Right: cleaned image with masked pixels in red.
    Table: every flag with the percentage of pixels that carry it, and whether we mask it."""
    target, frames = _load(text)
    det = parse_detectors(detector)[0]
    ids = sorted(set(frames["epoch"]))
    try:
        rows = frames[(frames["epoch"] == ids[visit]) & (frames["detector"] == det)]
        row = rows[frame]
    except IndexError:
        raise ValueError(f"No such {det} exposure in that visit.")
    pos = at_time(target, Time(row["mjd"], format="mjd"))
    f = clean_frame(get_cutout(row["access_url"], pos, 0.1))
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
