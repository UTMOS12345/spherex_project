"""Lesson 6 - group frames into survey visits (epochs) and stack each visit onto one sky grid."""
import warnings

import numpy as np
from astropy.convolution import Gaussian2DKernel, interpolate_replace_nans
from astropy.stats import sigma_clip
from astropy.utils.exceptions import AstropyUserWarning
from astropy.time import Time
from astropy.wcs import WCS
from reproject import reproject_interp

from .clean import clean_frame, BAD_FLAGS
from .download import get_cutouts
from . import framecache
from . import workers
from . import photometry as _phot
from .progress import report, CLEANING, STACKING
from .targets import at_time, at_times
from .text import plural

CLIP_SIGMA = 4.0          # stacking: a frame's pixel this far from the other frames is dropped
CLIP_MIN_FRAMES = 4       # ... only where at least this many frames cover the pixel
MAX_PICTURES = 150        # every-frame mode (days=0) refuses to build more pictures than this
BLOOM_RADIUS = 4          # clean_frame: how far from a saturated pixel a known star's flags are forgiven


def assign_epochs(frames, gap_days=30, max_len_days=60):
    """Frames table -> same table (sorted by time) with a new integer column 'epoch' (0, 1, 2...).
    A new epoch starts after a gap longer than gap_days, or when an epoch would get longer
    than max_len_days (targets near the ecliptic poles are observed almost continuously).
    max_len_days=0 (days=0): one epoch per exposure, i.e. per distinct time. SPHEREx exposes
    two detectors at once (D1+D4, D2+D5, D3+D6), so such a pair shares one epoch."""
    frames = frames.copy()
    frames.sort("mjd")
    if max_len_days <= 0:
        _, ids = np.unique(np.asarray(frames["mjd"], float), return_inverse=True)
        frames["epoch"] = ids
        return frames
    ids, epoch, start, last = [], 0, None, None
    for mjd in frames["mjd"]:
        if start is None:
            start = mjd                                   # very first frame
        elif mjd - last > gap_days or mjd - start > max_len_days:
            epoch += 1                                    # a new visit begins
            start = mjd
        ids.append(epoch)
        last = mjd
    frames["epoch"] = ids
    return frames


def make_grid(center, size_arcmin=4.0, pixscale_arcsec=3.0):
    """A blank north-up sky grid centred on a SkyCoord -> (WCS, shape).
    Every frame of every epoch is resampled onto this same grid."""
    n = int(round(size_arcmin * 60 / pixscale_arcsec))
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [center.ra.deg, center.dec.deg]         # this sky position...
    w.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]              # ...sits at the middle pixel
    w.wcs.cdelt = [-pixscale_arcsec / 3600, pixscale_arcsec / 3600]   # east left, north up
    return w, (n, n)


def central_min(coverage, frac=0.5):
    """Smallest value of a coverage map over its central area (the middle `frac` of each side),
    where the target is: how many frames the weakest part of the picture's centre rests on."""
    ny, nx = coverage.shape
    y0, x0 = int(ny * (1 - frac) / 2), int(nx * (1 - frac) / 2)
    return int(np.min(coverage[y0:ny - y0, x0:nx - x0]))


def stack_epoch(paths, grid_wcs, shape, bad_flags=BAD_FLAGS, keep_saturated_stars=True, wl_range=None,
                return_count=False, return_stats=False, clip=True, progress=None):
    """Cutout files of ONE epoch -> (stacked image, coverage map) on the common grid.
    Each frame is cleaned (Lesson 5), levelled to zero sky and reprojected; then, pixel by pixel:
      4 or more frames: sigma-clipped mean (CLIP_SIGMA, median centre, MAD spread), so one bad
                        frame cannot leave a hole or a spike;
      2 or 3 frames:    median (with 3 frames one bad value is ignored; with 2 the median is
                        the mean of the two, so a bad value still shows);
      1 frame:          that frame's value.
    A pixel that is bad in one frame is filled in by the others.
    clip=False: plain nanmean of all frames instead (no clipping, no median). Use it to see
    sources that are in only a few of the frames (fast movers, short flares), which the
    clipped stack suppresses.
    wl_range=(lo, hi) in micron: keep only pixels that see a wavelength in that range
    (a "narrow-band image"). Each frame then contributes only a stripe of pixels, so the
    picture fills in only where enough frames overlap.
    return_count=True also returns how many frames actually contributed.
    return_stats=True instead returns (stack, coverage, stats), stats = dict n (frames used),
    n_min (central_min of the coverage), n_values (pixel values that went in), n_rejected
    (of those, how many the sigma clipping dropped; 0 with clip=False), used (indices into
    `paths` of the frames that went into the stack).
    progress: optional callback (spherex.progress): "cleaning and aligning", once per frame."""
    report(progress, CLEANING, 0, len(paths))
    count = [0]

    def tick(_):
        count[0] += 1
        report(progress, CLEANING, count[0], len(paths))
    all_layers = _aligned_layers(list(paths), grid_wcs, shape, bad_flags, keep_saturated_stars, wl_range, tick)
    layers = [x for x in all_layers if x is not None]
    used_idx = [i for i, x in enumerate(all_layers) if x is not None]
    framecache.sweep()                                    # keep the frame cache under its cap
    return _combine_layers(layers, used_idx, shape, clip, return_count, return_stats)


def _aligned_layer(p, grid_wcs, shape, bad_flags, keep_saturated_stars, wl_range):
    """One cutout file -> its cleaned, sky-levelled picture on the grid, or None when the frame
    never sees wl_range. The per-frame half of stack_epoch. Served from the frame cache
    (spherex.framecache) when this frame was aligned onto this grid before with the same
    settings; the array is then the same, bit for bit."""
    return framecache.cached_layer(
        p, grid_wcs, shape, lambda: _compute_layer(p, grid_wcs, shape, bad_flags, keep_saturated_stars, wl_range),
        bad_flags, keep_saturated_stars, BLOOM_RADIUS, wl_range)


def grid_params(grid_wcs, shape):
    """A make_grid grid as plain numbers (for worker processes): rebuilding it with
    grid_from_params gives the same WCS, bit for bit. A WCS is never pickled: that goes
    through a FITS header and loses digits."""
    w = grid_wcs.wcs
    return {"ctype": [str(c) for c in w.ctype], "crval": [float(v) for v in w.crval],
            "crpix": [float(v) for v in w.crpix], "cdelt": [float(v) for v in w.cdelt],
            "shape": [int(n) for n in shape]}


def grid_from_params(p):
    """grid_params -> (WCS, shape), built the way make_grid builds it."""
    w = WCS(naxis=2)
    w.wcs.ctype = p["ctype"]
    w.wcs.crval = p["crval"]
    w.wcs.crpix = p["crpix"]
    w.wcs.cdelt = p["cdelt"]
    return w, tuple(p["shape"])


def _layer_task(path, grid, bad_flags, keep_saturated_stars, wl_range, use_cache, frame_dir):
    """One frame, in a worker process: rebuild the grid, then clean, align and store it in the
    frame cache (atomic write) exactly as _aligned_layer does -> the aligned frame or None."""
    from pathlib import Path
    framecache.FRAME_DIR = Path(frame_dir)            # the caller's cache folder
    grid_wcs, shape = grid_from_params(grid)
    return framecache.cached_layer(
        path, grid_wcs, shape, lambda: _compute_layer(path, grid_wcs, shape, list(bad_flags), keep_saturated_stars, wl_range),
        list(bad_flags), keep_saturated_stars, BLOOM_RADIUS, wl_range, use_cache=use_cache)


def _aligned_layers(paths, grid_wcs, shape, bad_flags, keep_saturated_stars, wl_range, on_done=None):
    """_aligned_layer for many files -> list in the same order. Frames in the frame cache are
    read here; the rest are cleaned and aligned by worker processes (spherex.workers,
    SPHEREX_WORKERS), which also store them. Same arrays for any number of workers.
    on_done(i): called in this thread as frame i is ready (progress)."""
    out = [None] * len(paths)
    misses = []
    for i, p in enumerate(paths):
        found, layer = framecache.lookup(p, grid_wcs, shape, bad_flags, keep_saturated_stars, BLOOM_RADIUS, wl_range)
        if found:
            out[i] = layer
            if on_done is not None:
                on_done(i)
        else:
            misses.append(i)
    if not misses:
        return out
    use_cache = framecache.enabled()
    grid = grid_params(grid_wcs, shape)
    rebuilt = grid_from_params(grid)
    if framecache.grid_key(*rebuilt) != framecache.grid_key(grid_wcs, shape):   # not a make_grid grid
        for i in misses:
            out[i] = _aligned_layer(paths[i], grid_wcs, shape, bad_flags, keep_saturated_stars, wl_range)
            if on_done is not None:
                on_done(i)
        return out
    tasks = [(str(paths[i]), grid, tuple(bad_flags), bool(keep_saturated_stars),
              None if wl_range is None else (float(wl_range[0]), float(wl_range[1])),
              use_cache, str(framecache.FRAME_DIR)) for i in misses]
    layers = workers.run(_layer_task, tasks, on_done=None if on_done is None else (lambda k: on_done(misses[k])))
    for i, layer in zip(misses, layers):
        out[i] = layer
    if use_cache:
        framecache.note_writes(len(misses))
    return out


def _compute_layer(p, grid_wcs, shape, bad_flags, keep_saturated_stars, wl_range):
    """_aligned_layer without the cache: clean, level, fill, cut to wl_range, reproject."""
    f = clean_frame(p, bad_flags, keep_saturated_stars, BLOOM_RADIUS)
    img = f["image"] - np.nanmedian(f["image"])           # remove what the ZODI model missed
    if keep_saturated_stars:
        # fill small holes (saturated star cores, masked neighbours) from the pixels around
        # them, so bright stars stay solid. For pictures only, not for photometry.
        img = interpolate_replace_nans(img, Gaussian2DKernel(1.5))
    if wl_range is not None:                              # AFTER the filling, so no colour leaks in
        wl = _phot.wavelength_map(p)
        outside = ~((wl >= wl_range[0]) & (wl <= wl_range[1]))
        if outside.all():
            return None                                   # this frame never sees that wavelength
        img = np.where(outside, np.nan, img)
    return reproject_interp((img, f["wcs"]), grid_wcs, shape_out=shape, return_footprint=False)


def _combine_layers(layers, used_idx, shape, clip=True, return_count=False, return_stats=False):
    """Aligned pictures of one epoch -> stack_epoch's result. The per-pixel half of stack_epoch."""
    if not layers:
        empty = (np.full(shape, np.nan), np.zeros(shape, int))
        if return_stats:
            return (*empty, {"n": 0, "n_min": 0, "n_values": 0, "n_rejected": 0, "used": []})
        return (*empty, 0) if return_count else empty
    cube = np.array(layers)                               # shape (n_frames, ny, nx)
    coverage = np.isfinite(cube).sum(axis=0)              # how many frames saw each pixel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # "mean of empty slice" where coverage = 0
        warnings.simplefilter("ignore", AstropyUserWarning)   # sigma_clip: "invalid values" = NaNs, masked as wanted
        stack = np.nanmean(cube, axis=0)                  # 1 frame: its value (clip=False: everywhere)
        rejected = 0
        few = (coverage >= 2) & (coverage < CLIP_MIN_FRAMES)
        if clip and few.any():                            # 2-3 frames: the median
            stack = np.where(few, np.nanmedian(cube, axis=0), stack)
        if clip and len(layers) >= CLIP_MIN_FRAMES:
            # One bad frame (an unflagged hole of -50 where the sky is ~0) would otherwise
            # survive the mean as a -150 sigma blob, and as a fake source in differences.
            # Each pixel is clipped against its own frames (median, MAD spread), so a star
            # that is in every frame keeps its own centre and is not clipped.
            clipped = sigma_clip(cube, sigma=CLIP_SIGMA, maxiters=3, cenfunc="median",
                                 stdfunc="mad_std", axis=0, masked=True)
            robust = np.ma.mean(clipped, axis=0).filled(np.nan)
            stack = np.where(coverage >= CLIP_MIN_FRAMES, robust, stack)
            used = coverage >= CLIP_MIN_FRAMES                   # only where the clipped mean is kept
            rejected = int((np.ma.getmaskarray(clipped) & np.isfinite(cube))[:, used].sum())
    if return_stats:
        return stack, coverage, {"n": len(layers), "n_min": central_min(coverage),
                                 "n_values": int(coverage.sum()), "n_rejected": rejected, "used": used_idx}
    return (stack, coverage, len(layers)) if return_count else (stack, coverage)


def parse_detectors(detector):
    """Detector choice -> list like ['D5', 'D6'].
    Accepts 2, 'D2', 'd2', 'D5+D6', '5+6', 'D5,D6', ['D5', 6], or 'all' (all six)."""
    if isinstance(detector, (list, tuple, set)):
        parts = list(detector)
    elif str(detector).strip().lower() == "all":
        parts = range(1, 7)
    else:
        parts = str(detector).replace(",", "+").replace(" ", "+").split("+")
    out = []
    for p in parts:
        p = str(p).strip().upper().removeprefix("D")
        if not p:
            continue
        if not p.isdigit() or not 1 <= int(p) <= 6:
            raise ValueError(f"Unknown detector {p!r}: use D1..D6, combinations like D5+D6, or 'all'.")
        if f"D{int(p)}" not in out:
            out.append(f"D{int(p)}")
    if not out:
        raise ValueError("No detector given.")
    return sorted(out)


def epoch_grid(frames, target, grid_arcmin=4.0, pixscale_arcsec=3.0):
    """The one sky grid all epochs of make_epochs share -> (wcs, shape): centred on the target
    in the middle of the frames' time span. spherex.results rebuilds a saved stack's WCS with
    this instead of storing it (a WCS saved as a FITS header loses its last digits)."""
    t_mid = Time((frames["mjd"].min() + frames["mjd"].max()) / 2, format="mjd")
    return make_grid(at_time(target, t_mid), grid_arcmin, pixscale_arcsec)


def make_epochs(frames, target, detector=None, size_deg=None, grid_arcmin=4.0, pixscale_arcsec=3.0,
                gap_days=30, max_len_days=60, bad_flags=BAD_FLAGS, keep_saturated_stars=True,
                wl_range=None, clip=True, progress=None):
    """The whole Lesson 6 chain.
    frames table + target SkyCoord + detector -> list of dicts, one per epoch:
    epoch, detector, mjd, date, first_mjd, last_mjd (of the frames used), releases, visit (the
    frames table's own 'epoch' number, e.g. api.visits', for most of the frames used; -1 if the
    table had none), n_frames, n_min (fewest frames under the centre, per detector),
    clipped_fraction (share of pixel values the sigma clipping rejected), detectors_used,
    wl_range, clip, image, coverage, wcs.
    clip: see stack_epoch (True = sigma-clipped / median stacks, False = plain nanmean).
    All epochs share ONE grid fixed on the sky, so a moving star changes pixel between epochs.
    grid_arcmin is the field of view (width of the picture). The cutout size follows from it
    unless size_deg is given; up to ~10' is served from the standard 0.25 deg downloads.
    Smaller gap_days / max_len_days cut the visits into shorter pieces: more pictures,
    each made from fewer frames (noisier).
    max_len_days=0 (api days=0): every-frame mode, one picture per exposure, each frame cleaned
    and reprojected on its own (no clipping; n_min is at most 1, so every picture counts as
    "few frames"); date then includes the time (YYYY-MM-DD HH:MM). More than MAX_PICTURES
    pictures raise ValueError.
    detector: one ('D2' or 2) or several combined ('D5+D6', ['D5', 'D6'], 'all'), like
    WiseView's W1 / W2 / W1+W2. With several, each detector is stacked on its own first and the
    stacks are then averaged, so every detector counts equally however many frames it has.
    wl_range: (lo, hi) in micron -> narrow-band pictures, only pixels seeing that wavelength.
    With wl_range, detector may be None: the detectors covering the range are chosen.
    progress: optional callback (spherex.progress): "downloading images" (every frame),
    "cleaning and aligning" (every frame that arrived), then "stacking visits" (per picture)."""
    if wl_range is not None:
        wl_range = (float(min(wl_range)), float(max(wl_range)))
    if detector is None:
        if wl_range is None:
            raise ValueError("Give a detector or a wavelength range.")
        lo = np.asarray(frames["em_min"], float) * 1e6
        hi = np.asarray(frames["em_max"], float) * 1e6
        covering = (lo <= wl_range[1]) & (hi >= wl_range[0])
        dets = sorted(set(str(d) for d in frames["detector"][covering]))
        if not dets:
            raise ValueError(f"No detector covers {wl_range[0]}-{wl_range[1]} micron.")
    else:
        dets = parse_detectors(detector)
    det = "+".join(dets) if wl_range is None else f"{wl_range[0]:g}-{wl_range[1]:g}um"
    if size_deg is None:     # the cutout must cover the grid whatever the frame's rotation (x 1.5)
        size_deg = round(max(0.1, grid_arcmin / 60 * 1.5), 3)
    frames = frames.copy()                    # the caller's visit numbers (api.visits), if it has them
    frames["source_visit"] = np.asarray(frames["epoch"]) if "epoch" in frames.colnames else -1
    frames = assign_epochs(frames, gap_days, max_len_days)
    every = max_len_days <= 0
    if every:
        clip = False                          # one frame per picture: nothing to clip against
        n_pics = len(set(frames["epoch"][np.isin(frames["detector"], dets)]))
        if n_pics > MAX_PICTURES:
            raise ValueError(f"One picture per frame would make {n_pics} pictures (at most {MAX_PICTURES}). "
                             "Use weekly pictures, or one detector instead of several.")
    grid_wcs, shape = epoch_grid(frames, target, grid_arcmin, pixscale_arcsec)

    # Three passes, so each stage reports one running count (progress): 1. download every
    # frame, 2. clean and align every frame that arrived, 3. combine each epoch. Same frames,
    # same order and same arithmetic as stacking epoch by epoch.
    plan, requests = [], []                               # plan: (epoch, rows, [(det, [(row, i)])])
    mjds = sorted(set(float(m) for m in frames["mjd"][np.isin(frames["detector"], dets)]))
    where = dict(zip(mjds, at_times(target, mjds)))       # the target on each frame's date
    for e in sorted(set(frames["epoch"])):
        rows = frames[(frames["epoch"] == e) & np.isin(frames["detector"], dets)]
        per_det = []
        for d in dets:
            items = []
            for row in rows[rows["detector"] == d]:
                center = where[float(row["mjd"])]                # same centre as prefetch
                items.append((row, len(requests)))
                requests.append((row["access_url"], center, size_deg))
            per_det.append((d, items))
        plan.append((e, rows, per_det))
    # a cutout whose aligned frame is already in the frame cache is not opened to check it
    trusted = lambda path: framecache.has(path, grid_wcs, shape, bad_flags, keep_saturated_stars,
                                          BLOOM_RADIUS, wl_range)
    results = get_cutouts(requests, progress, trusted=trusted)   # path, or the OSError for that frame

    order = [i for _, _, per_det in plan for _, items in per_det for _, i in items
             if not isinstance(results[i], OSError)]     # the arrived frames, in plan order
    report(progress, CLEANING, 0, len(order))
    done = [0]

    def tick(_):
        done[0] += 1
        report(progress, CLEANING, done[0], len(order))
    layer_of = dict(zip(order, _aligned_layers([results[i] for i in order], grid_wcs, shape, bad_flags,
                                               keep_saturated_stars, wl_range, tick)))
    aligned = []                                          # (epoch, rows, skipped, [(det, layers, used, path_rows)])
    for e, rows, per_det in plan:
        skipped, groups = {}, []
        for d, items in per_det:
            layers, used_idx, path_rows = [], [], []
            for row, i in items:
                if isinstance(results[i], OSError):
                    skipped[str(results[i])] = skipped.get(str(results[i]), 0) + 1
                    continue
                layer = layer_of[i]
                if layer is not None:
                    layers.append(layer)
                    used_idx.append(len(path_rows))       # index into this detector's arrived frames
                path_rows.append(row)
            groups.append((d, layers, used_idx, path_rows))
        aligned.append((e, rows, skipped, groups))
    layer_of = None
    framecache.sweep()                                    # keep the frame cache under its cap

    epochs = []
    report(progress, STACKING, 0, len(aligned))
    for i_ep, (e, rows, skipped, groups) in enumerate(aligned):
        stacks, coverages, used, have, n_mins, n_vals, n_rej = [], [], 0, [], [], 0, 0
        used_rows = []                                    # the frames that went into the picture
        for d, layers, used_idx, path_rows in groups:
            if path_rows:
                st, cov, stats = _combine_layers(layers, used_idx, shape, clip, return_stats=True)
                if stats["n"] == 0:
                    continue                              # no frame of this detector saw the range
                stacks.append(st); coverages.append(cov); used += stats["n"]; have.append(d)
                used_rows += [path_rows[i] for i in stats["used"]]
                n_mins.append(stats["n_min"]); n_vals += stats["n_values"]; n_rej += stats["n_rejected"]
        aligned[i_ep] = None                              # free the aligned frames of this epoch
        for reason, count in skipped.items():
            print(f"  epoch {e}: skipped {plural(count, 'frame')}: {reason}")
        if not stacks or all(np.isnan(x).all() for x in stacks):
            report(progress, STACKING, i_ep + 1, len(aligned))
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            stack = np.nanmean(np.array(stacks), axis=0) if len(stacks) > 1 else stacks[0]
        coverage = np.sum(coverages, axis=0)
        mjd = float(np.mean(rows["mjd"]))
        src = [int(r["source_visit"]) for r in used_rows]
        epochs.append({"first_mjd": float(min(r["mjd"] for r in used_rows)),
                       "last_mjd": float(max(r["mjd"] for r in used_rows)),
                       "releases": ", ".join(sorted({str(r["collection"]).removeprefix("spherex_").upper()
                                                     for r in used_rows if "collection" in r.colnames})),
                       "visit": max(set(src), key=lambda v: (src.count(v), -v)),   # most frames; ties: earlier
                       "epoch": int(e), "detector": det, "mjd": mjd,
                       "date": Time(mjd, format="mjd").iso[:16 if every else 10], "n_frames": used,
                       "detectors_used": "+".join(have), "wl_range": wl_range,
                       "n_min": min(n_mins),             # weakest per-detector frame count in the centre
                       "clipped_fraction": n_rej / n_vals if n_vals else 0.0, "clip": bool(clip),
                       "image": stack, "coverage": coverage, "wcs": grid_wcs})
        report(progress, STACKING, i_ep + 1, len(aligned))
    return epochs
