"""Lesson 6 - group frames into survey visits (epochs) and stack each visit onto one sky grid."""
import warnings

import numpy as np
from astropy.convolution import Gaussian2DKernel, interpolate_replace_nans
from astropy.time import Time
from astropy.wcs import WCS
from reproject import reproject_interp

from .clean import clean_frame, BAD_FLAGS
from .download import get_cutout
from .targets import at_time


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


def stack_epoch(paths, grid_wcs, shape, bad_flags=BAD_FLAGS, keep_saturated_stars=True):
    """Cutout files of ONE epoch -> (stacked image, coverage map) on the common grid.
    Each frame is cleaned (Lesson 5), levelled to zero sky, reprojected, then averaged
    with nanmean, so a pixel that is bad in one frame is filled in by the others."""
    layers = []
    for p in paths:
        f = clean_frame(p, bad_flags, keep_saturated_stars)
        img = f["image"] - np.nanmedian(f["image"])       # remove what the ZODI model missed
        if keep_saturated_stars:
            # fill small holes (saturated star cores, masked neighbours) from the pixels around
            # them, so bright stars stay solid. For pictures only, not for photometry.
            img = interpolate_replace_nans(img, Gaussian2DKernel(1.5))
        layers.append(reproject_interp((img, f["wcs"]), grid_wcs,
                                       shape_out=shape, return_footprint=False))
    if not layers:
        return np.full(shape, np.nan), np.zeros(shape, int)
    cube = np.array(layers)                               # shape (n_frames, ny, nx)
    coverage = np.isfinite(cube).sum(axis=0)              # how many frames saw each pixel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # "mean of empty slice" where coverage = 0
        stack = np.nanmean(cube, axis=0)
    return stack, coverage


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


def make_epochs(frames, target, detector, size_deg=None, grid_arcmin=4.0, pixscale_arcsec=3.0,
                gap_days=30, max_len_days=60, bad_flags=BAD_FLAGS, keep_saturated_stars=True):
    """The whole Lesson 6 chain.
    frames table + target SkyCoord + detector -> list of dicts, one per epoch:
    epoch, detector, mjd, date, n_frames, image, coverage, wcs.
    All epochs share ONE grid fixed on the sky, so a moving star changes pixel between epochs.
    grid_arcmin is the field of view (width of the picture). The cutout size follows from it
    unless size_deg is given; up to ~10' is served from the standard 0.25 deg downloads.
    Smaller gap_days / max_len_days cut the visits into shorter pieces: more pictures,
    each made from fewer frames (noisier).
    detector: one ('D2' or 2) or several combined ('D5+D6', ['D5', 'D6'], 'all'), like
    WiseView's W1 / W2 / W1+W2. With several, each detector is stacked on its own first and the
    stacks are then averaged, so every detector counts equally however many frames it has."""
    dets = parse_detectors(detector)
    det = "+".join(dets)
    if size_deg is None:     # the cutout must cover the grid whatever the frame's rotation (x 1.5)
        size_deg = round(max(0.1, grid_arcmin / 60 * 1.5), 3)
    frames = assign_epochs(frames, gap_days, max_len_days)
    t_mid = Time((frames["mjd"].min() + frames["mjd"].max()) / 2, format="mjd")
    grid_wcs, shape = make_grid(at_time(target, t_mid), grid_arcmin, pixscale_arcsec)

    epochs = []
    for e in sorted(set(frames["epoch"])):
        rows = frames[(frames["epoch"] == e) & np.isin(frames["detector"], dets)]
        stacks, coverages, used, have = [], [], 0, []
        for d in dets:
            paths = []
            for row in rows[rows["detector"] == d]:
                center = at_time(target, Time(row["mjd"], format="mjd"))   # same centre as prefetch
                try:
                    paths.append(get_cutout(row["access_url"], center, size_deg))
                except OSError as err:
                    print(f"  epoch {e}: skipped {row['obs_id']} {d} ({err})")
            if paths:
                st, cov = stack_epoch(paths, grid_wcs, shape, bad_flags, keep_saturated_stars)
                stacks.append(st); coverages.append(cov); used += len(paths); have.append(d)
        if not stacks:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            stack = np.nanmean(np.array(stacks), axis=0) if len(stacks) > 1 else stacks[0]
        coverage = np.sum(coverages, axis=0)
        mjd = float(np.mean(rows["mjd"]))
        epochs.append({"epoch": int(e), "detector": det, "mjd": mjd,
                       "date": Time(mjd, format="mjd").iso[:10], "n_frames": used,
                       "detectors_used": "+".join(have),
                       "image": stack, "coverage": coverage, "wcs": grid_wcs})
    return epochs
