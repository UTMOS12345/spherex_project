"""Blind search: residuals in the differences between visits of one field, without being told
where to look.

The input is the list of per-visit stacks make_epochs() returns (all on one sky grid). For each
pair of visits the difference image (spherex.diff.difference: later minus earlier) is searched
for positive and negative residuals; spherex.combine.minus_mean (each visit minus the mean of
the others) is the alternative input (method="minus_mean").

A residual is NOT a detection. Most residuals in SPHEREx visit differences are artefacts: a
star whose point-spread function looks different in the two visits (the focal plane is turned
differently on each visit), the wings and rings of saturated stars, frame edges, pixels covered
by only a few frames. This module only lists residuals and the evidence about them.

Stacking and fast movers: the default sigma-clipped stack (clip=True in make_epochs) drops a
pixel value that differs from the other frames of the visit by more than CLIP_SIGMA, so a source
that is in only part of a visit - an asteroid, a flare, anything that moves a lot during the
visit - is suppressed. clip=False (plain average) keeps those sources, but also keeps
single-frame defects (cosmic rays, unflagged bad pixels, satellite trails), which then show up
as residuals too. The search takes the stacks as they were made; api.find_movers has `clip`.
"""
import warnings

import numpy as np
from astropy.convolution import Gaussian2DKernel, convolve
from astropy.stats import gaussian_fwhm_to_sigma, sigma_clipped_stats
from astropy.table import Table
from photutils.segmentation import SourceCatalog, detect_sources
from photutils.utils.exceptions import NoDetectionsWarning

from .combine import minus_mean
from .diff import difference

DETECT_SIGMA = 5.0      # a residual must peak this many noise sigmas above zero (smoothed image)
SMOOTH_FWHM_PX = 2.0    # detection filter: Gaussian of this FWHM in grid pixels (6" at 3"/px)
MIN_AREA_PX = 5         # ... and cover at least this many connected grid pixels above threshold

COLUMNS = ["pair", "visit_a", "visit_b", "date_a", "date_b", "mjd_a", "mjd_b", "sign", "x", "y",
           "ra", "dec", "significance", "peak", "flux", "area_px", "noise"]
DTYPES = {c: float for c in COLUMNS} | {"pair": str, "date_a": str, "date_b": str, "visit_a": int,
                                        "visit_b": int, "sign": int, "area_px": int}


def pairs_of(n, pairs="consecutive"):
    """Visit index pairs (earlier, later) to difference: 'consecutive' -> (0,1), (1,2), ...;
    'all' -> every pair (more baseline for slow movers, but the pairs are not independent)."""
    if pairs == "consecutive":
        return [(i, i + 1) for i in range(n - 1)]
    if pairs == "all":
        return [(i, j) for i in range(n) for j in range(i + 1, n)]
    raise ValueError("pairs must be 'consecutive' or 'all'.")


def robust_noise(img, valid=None):
    """Sigma-clipped standard deviation of the finite (and valid) pixels of img."""
    ok = np.isfinite(img) if valid is None else (valid & np.isfinite(img))
    if ok.sum() < 50:
        return np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(sigma_clipped_stats(img[ok], sigma=3.0, maxiters=10)[2])


def _smooth(img, fwhm_px):
    kernel = Gaussian2DKernel(fwhm_px * gaussian_fwhm_to_sigma)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return convolve(np.nan_to_num(img), kernel, normalize_kernel=True)


def _centroid(source):
    """(x, y) of a SourceCatalog row: photutils >= 3 names them x_centroid, older xcentroid."""
    if hasattr(type(source), "x_centroid"):
        return float(source.x_centroid), float(source.y_centroid)
    return float(source.xcentroid), float(source.ycentroid)


def detect_residuals(image, valid, nsigma=DETECT_SIGMA, fwhm_px=SMOOTH_FWHM_PX, min_area=MIN_AREA_PX):
    """Positive and negative residuals in one difference image -> list of dicts
    (sign, x, y, significance, peak, flux, area_px, noise).
    The image is smoothed with a Gaussian (fwhm_px), the noise is the sigma-clipped std of the
    smoothed image over the valid pixels, and connected areas of at least min_area pixels above
    nsigma x noise are residuals - found for the image and for minus the image separately, so a
    dipole gives one positive and one negative residual. significance = the smoothed peak in
    noise units; x, y = flux-weighted centroid (grid pixels); peak, flux on the unsmoothed image."""
    valid = valid & np.isfinite(image)
    data = np.where(valid, image, 0.0)
    smooth = _smooth(data, fwhm_px)
    noise_s = robust_noise(smooth, valid)
    noise = robust_noise(image, valid)
    out = []
    if not np.isfinite(noise_s) or noise_s <= 0:
        return out
    for sign in (1, -1):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NoDetectionsWarning)
            # pixel count positional: photutils < 3 calls it npixels, >= 3 n_pixels
            segm = detect_sources(sign * smooth, nsigma * noise_s, min_area, mask=~valid)
        if segm is None:
            continue
        cat = SourceCatalog(np.where(valid, sign * data, 0.0), segm, convolved_data=sign * smooth,
                            mask=~valid)
        for s in cat:
            x, y = _centroid(s)
            out.append({"sign": sign, "x": x, "y": y,
                        "significance": float(s.max_value / noise_s),
                        "peak": float(sign * np.nanmax(np.where(segm.data == s.label, sign * data, -np.inf))),
                        "flux": float(sign * s.segment_flux), "area_px": int(s.area.value),
                        "noise": noise})
    return out


def _rows(found, wcs, label, a, b, ep_a, ep_b):
    rows = []
    for r in found:
        sky = wcs.pixel_to_world(r["x"], r["y"])
        rows.append({"pair": label, "visit_a": a, "visit_b": b, "date_a": ep_a["date"], "date_b": ep_b["date"],
                     "mjd_a": float(ep_a["mjd"]), "mjd_b": float(ep_b["mjd"]),
                     "ra": float(sky.ra.deg), "dec": float(sky.dec.deg), **r})
    return rows


def residual_images(epochs, method="pairs", pairs="consecutive"):
    """The images to search -> list of (label, a, b, image): a, b index epochs (a earlier,
    b later; for minus_mean b is the visit and a is -1, 'the mean of the others').
    pairs: method 'pairs' -> difference(later, earlier) for each pair of pairs_of(...)
           method 'minus_mean' -> each visit minus the mean of the others (combine.minus_mean)."""
    if method == "pairs":
        return [(f"{a}-{b}", a, b, difference(epochs[b], epochs[a])["image"])
                for a, b in pairs_of(len(epochs), pairs)]
    if method == "minus_mean":
        if len(epochs) < 3:      # with two visits minus_mean is just the pair difference, twice
            return residual_images(epochs, "pairs", pairs)
        return [(f"{i}-mean", -1, i, e["image"]) for i, e in enumerate(minus_mean(epochs))]
    raise ValueError("method must be 'pairs' or 'minus_mean'.")


def find_residuals(epochs, nsigma=DETECT_SIGMA, method="pairs", pairs="consecutive",
                   fwhm_px=SMOOTH_FWHM_PX, min_area=MIN_AREA_PX):
    """Stacked visits of one field (make_epochs) -> Table of residuals (COLUMNS), every image of
    residual_images() searched with detect_residuals(). Sorted by image, then by significance
    (highest first), then position, so the same stacks always give the same table."""
    if len(epochs) < 2:
        raise ValueError("A search needs at least 2 visits.")
    wcs = epochs[0]["wcs"]
    rows = []
    for label, a, b, img in residual_images(epochs, method, pairs):
        ep_b = epochs[b]
        ep_a = epochs[a] if a >= 0 else {"date": "mean of the others", "mjd": np.nan}
        valid = np.isfinite(img) & (epochs[b]["coverage"] > 0)
        if a >= 0:
            valid &= epochs[a]["coverage"] > 0
        rows += _rows(detect_residuals(img, valid, nsigma, fwhm_px, min_area), wcs, label, a, b, ep_a, ep_b)
    rows.sort(key=lambda r: (r["visit_b"], r["visit_a"], -r["significance"], round(r["x"], 6), round(r["y"], 6)))
    if not rows:
        return Table(names=COLUMNS, dtype=[DTYPES[c] for c in COLUMNS])
    return Table(rows=[[r[c] for c in COLUMNS] for r in rows], names=COLUMNS)
