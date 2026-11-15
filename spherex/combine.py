"""Adding and subtracting pictures: over time (visits) and across colours (detectors).

All inputs are epochs from make_epochs(). Epochs made from the SAME frames table share one
grid, so they can be combined pixel by pixel (also across detectors).
"""
import warnings

import numpy as np
from astropy.visualization import ZScaleInterval, AsinhStretch

from .diff import difference
from .text import plural


def _mean(images):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(np.array(images), axis=0)


def deep_image(epochs):
    """ADD all visits -> one deep picture (dict like an epoch). Faintest things show best;
    moving objects appear as a short trail or several dots."""
    ep = dict(epochs[0])
    ep["image"] = _mean([e["image"] for e in epochs])
    ep["n_frames"] = sum(e["n_frames"] for e in epochs)
    ep["date"] = f"{epochs[0]['date']} to {epochs[-1]['date']}"
    ep["label"] = f"{'all ' if len(epochs) > 1 else ''}{plural(len(epochs), 'visit')} added"
    return ep


def minus_mean(epochs):
    """Each visit MINUS the average of all the OTHER visits -> list of epochs.
    Everything constant cancels; what moved or changed lights up in every picture
    (bright where it is now, dark where it was on the other dates)."""
    out = []
    for i, ep in enumerate(epochs):
        others = [e["image"] for j, e in enumerate(epochs) if j != i]
        e2 = dict(ep)
        e2["image"] = ep["image"] - _mean(others) if others else ep["image"] * np.nan
        e2["label"] = f"{ep['date']} minus the other visits"
        out.append(e2)
    return out


def difference_series(epochs, ref=0):
    """Each visit MINUS one reference visit (default: the first) -> list of epochs.
    As a flipbook, a moving object walks away from the dark hole it left behind."""
    out = []
    for ep in epochs:
        e2 = dict(ep)
        e2["image"] = ep["image"] - epochs[ref]["image"]
        e2["label"] = f"{ep['date']} minus {epochs[ref]['date']}"
        out.append(e2)
    return out


def band_difference(epoch_long, epoch_short):
    """Same visit, two colours: long-wavelength picture MINUS short-wavelength picture,
    scaled so that typical stars cancel. What remains has an unusual colour - a very cold
    object (bright at long wavelengths) stays bright, ordinary stars vanish.
    Both epochs must come from make_epochs() on the same frames table (same grid)."""
    d = difference(epoch_long, epoch_short, match_scale=True)
    d["label"] = (f"{epoch_long['detector']} minus {d['scale']:.2f} x {epoch_short['detector']}"
                  f"  ({epoch_long['date']})")
    return d


def rgb_image(red, green, blue, contrast=0.25):
    """Three pictures (long, middle, short wavelength) -> colour image (ny, nx, 3), values 0..1.
    Each colour is stretched on its own (ZScale + Asinh), as in most astronomy colour images:
    very cold objects come out red, hot stars blue-white."""
    channels = []
    for img in (red, green, blue):
        ok = np.isfinite(img)
        vmin, vmax = ZScaleInterval(contrast=contrast).get_limits(img[ok]) if ok.any() else (0, 1)
        x = np.clip((np.nan_to_num(img, nan=vmin) - vmin) / ((vmax - vmin) or 1), 0, 1)
        channels.append(AsinhStretch()(x))
    return np.dstack(channels)
