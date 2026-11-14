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
from .download import get_cutout
from . import photometry as _phot
from .targets import at_time

CLIP_SIGMA = 4.0          # stacking: a frame's pixel this far from the other frames is dropped
CLIP_MIN_FRAMES = 4       # ... only where at least this many frames cover the pixel


def assign_epochs(frames, gap_days=30, max_len_days=60):
    """Frames table -> same table (sorted by time) with a new integer column 'epoch' (0, 1, 2...).
    A new epoch starts after a gap longer than gap_days, or when an epoch would get longer
    than max_len_days (targets near the ecliptic poles are observed almost continuously)."""
    frames = frames.copy()
    frames.sort("mjd")
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
                return_count=False, return_stats=False, clip=True):
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
    (of those, how many the sigma clipping dropped; 0 with clip=False)."""
    layers = []
    for p in paths:
        f = clean_frame(p, bad_flags, keep_saturated_stars)
        img = f["image"] - np.nanmedian(f["image"])       # remove what the ZODI model missed
        if keep_saturated_stars:
            # fill small holes (saturated star cores, masked neighbours) from the pixels around
            # them, so bright stars stay solid. For pictures only, not for photometry.
            img = interpolate_replace_nans(img, Gaussian2DKernel(1.5))
        if wl_range is not None:                          # AFTER the filling, so no colour leaks in
            wl = _phot.wavelength_map(p)
            outside = ~((wl >= wl_range[0]) & (wl <= wl_range[1]))
            if outside.all():
                continue                                  # this frame never sees that wavelength
            img = np.where(outside, np.nan, img)
        layers.append(reproject_interp((img, f["wcs"]), grid_wcs,
                                       shape_out=shape, return_footprint=False))
    if not layers:
        empty = (np.full(shape, np.nan), np.zeros(shape, int))
        if return_stats:
            return (*empty, {"n": 0, "n_min": 0, "n_values": 0, "n_rejected": 0})
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
                                 "n_values": int(coverage.sum()), "n_rejected": rejected}
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
            raise ValueError(f"unknown detector {p!r}: use D1..D6, combinations like D5+D6, or 'all'")
        if f"D{int(p)}" not in out:
            out.append(f"D{int(p)}")
    if not out:
        raise ValueError("no detector given")
    return sorted(out)


def make_epochs(frames, target, detector=None, size_deg=None, grid_arcmin=4.0, pixscale_arcsec=3.0,
                gap_days=30, max_len_days=60, bad_flags=BAD_FLAGS, keep_saturated_stars=True,
                wl_range=None, clip=True):
    """The whole Lesson 6 chain.
    frames table + target SkyCoord + detector -> list of dicts, one per epoch:
    epoch, detector, mjd, date, n_frames, n_min (fewest frames under the centre, per detector),
    clipped_fraction (share of pixel values the sigma clipping rejected), detectors_used,
    wl_range, clip, image, coverage, wcs.
    clip: see stack_epoch (True = sigma-clipped / median stacks, False = plain nanmean).
    All epochs share ONE grid fixed on the sky, so a moving star changes pixel between epochs.
    grid_arcmin is the field of view (width of the picture). The cutout size follows from it
    unless size_deg is given; up to ~10' is served from the standard 0.25 deg downloads.
    Smaller gap_days / max_len_days cut the visits into shorter pieces: more pictures,
    each made from fewer frames (noisier).
    detector: one ('D2' or 2) or several combined ('D5+D6', ['D5', 'D6'], 'all'), like
    WiseView's W1 / W2 / W1+W2. With several, each detector is stacked on its own first and the
    stacks are then averaged, so every detector counts equally however many frames it has.
    wl_range: (lo, hi) in micron -> narrow-band pictures, only pixels seeing that wavelength.
    With wl_range, detector may be None: the detectors covering the range are chosen."""
    if wl_range is not None:
        wl_range = (float(min(wl_range)), float(max(wl_range)))
    if detector is None:
        if wl_range is None:
            raise ValueError("give a detector, or a wavelength range")
        lo = np.asarray(frames["em_min"], float) * 1e6
        hi = np.asarray(frames["em_max"], float) * 1e6
        covering = (lo <= wl_range[1]) & (hi >= wl_range[0])
        dets = sorted(set(str(d) for d in frames["detector"][covering]))
        if not dets:
            raise ValueError(f"no detector covers {wl_range[0]}-{wl_range[1]} micron")
    else:
        dets = parse_detectors(detector)
    det = "+".join(dets) if wl_range is None else f"{wl_range[0]:g}-{wl_range[1]:g}um"
    if size_deg is None:     # the cutout must cover the grid whatever the frame's rotation (x 1.5)
        size_deg = round(max(0.1, grid_arcmin / 60 * 1.5), 3)
    frames = assign_epochs(frames, gap_days, max_len_days)
    t_mid = Time((frames["mjd"].min() + frames["mjd"].max()) / 2, format="mjd")
    grid_wcs, shape = make_grid(at_time(target, t_mid), grid_arcmin, pixscale_arcsec)

    epochs = []
    for e in sorted(set(frames["epoch"])):
        rows = frames[(frames["epoch"] == e) & np.isin(frames["detector"], dets)]
        stacks, coverages, used, have, skipped, n_mins, n_vals, n_rej = [], [], 0, [], {}, [], 0, 0
        for d in dets:
            paths = []
            for row in rows[rows["detector"] == d]:
                center = at_time(target, Time(row["mjd"], format="mjd"))   # same centre as prefetch
                try:
                    paths.append(get_cutout(row["access_url"], center, size_deg))
                except OSError as err:
                    skipped[str(err)] = skipped.get(str(err), 0) + 1
            if paths:
                st, cov, stats = stack_epoch(paths, grid_wcs, shape, bad_flags, keep_saturated_stars, wl_range,
                                             return_stats=True, clip=clip)
                if stats["n"] == 0:
                    continue                              # no frame of this detector saw the range
                stacks.append(st); coverages.append(cov); used += stats["n"]; have.append(d)
                n_mins.append(stats["n_min"]); n_vals += stats["n_values"]; n_rej += stats["n_rejected"]
        for reason, count in skipped.items():
            print(f"  epoch {e}: skipped {count} frame(s): {reason}")
        if not stacks or all(np.isnan(x).all() for x in stacks):
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            stack = np.nanmean(np.array(stacks), axis=0) if len(stacks) > 1 else stacks[0]
        coverage = np.sum(coverages, axis=0)
        mjd = float(np.mean(rows["mjd"]))
        epochs.append({"epoch": int(e), "detector": det, "mjd": mjd,
                       "date": Time(mjd, format="mjd").iso[:10], "n_frames": used,
                       "detectors_used": "+".join(have), "wl_range": wl_range,
                       "n_min": min(n_mins),             # weakest per-detector frame count in the centre
                       "clipped_fraction": n_rej / n_vals if n_vals else 0.0, "clip": bool(clip),
                       "image": stack, "coverage": coverage, "wcs": grid_wcs})
    return epochs
