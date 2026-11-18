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


# ------------------------------------------------------------------ 2. artefact cuts
MIN_FRAMES = 4          # a residual needs this many frames under it in BOTH visits (= CLIP_MIN_FRAMES)
EDGE_PX = 5             # ... and must lie this far inside the area both visits cover well
SAT_FLAGS = ("MP_OVERFLOW", "MP_BLOOM")   # a pixel with either is part of a saturated core
SAT_MIN_FRAMES = 2      # a grid pixel is saturated when this many frames of the visit say so
SAT_MIN_AREA_PX = 3     # smaller saturated patches are single hits, not stars
SAT_RING_FACTOR = 2.5   # around a saturated core of radius r: residuals out to 2.5 r + SAT_PAD_PX
SAT_PAD_PX = 4          #   are its wings and rings (R Draconis); not tuned on R Draconis (no local data)
SAT_MOVE_PX = 0.5       # a saturated star whose centroid moved more than this between visits moved:
                        #   static saturated stars in the Barnard's Star field move 0.01-0.13 px
REPEAT_PX = 2.0         # residuals of different images within this distance are "the same place"
MIN_CHANGE = 0.3        # a residual smaller than this fraction of the star under it is that star seen
                        #   slightly differently (point-spread function, a few % calibration between
                        #   releases): 5-25% for most residuals of the Barnard's Star field, 57-93% for
                        #   the lobes of Barnard's Star itself. Real changes smaller than 30% are lost.

CUTS = ("low coverage", "edge", "saturated star wings", "small change")


def visit_paths(frames, target, epochs, detector_list, size_deg, gap_days=30, max_len_days=60):
    """The cutout files each stacked visit was made from -> list (one per epoch) of paths,
    rebuilt the way make_epochs grouped and requested them (assign_epochs, the target's position
    on each frame's date). Frames whose file is not in the cache are left out."""
    from astropy.time import Time
    from .download import find_cached
    from .epochs import assign_epochs
    from .targets import at_time
    f = assign_epochs(frames.copy(), gap_days, max_len_days)
    out = []
    for ep in epochs:
        dets = str(ep.get("detectors_used") or "+".join(detector_list)).split("+")
        rows = f[(f["epoch"] == ep["epoch"]) & np.isin(f["detector"], dets)]
        paths = [find_cached(r["access_url"], at_time(target, Time(float(r["mjd"]), format="mjd")), size_deg)
                 for r in rows]
        out.append([p for p in paths if p is not None])
    return out


def saturation_map(paths, grid_wcs, shape, min_frames=SAT_MIN_FRAMES):
    """Cutout files of one visit -> bool map on the grid: True where at least min_frames frames
    flag the pixel OVERFLOW or BLOOM (a saturated star core)."""
    from astropy.io import fits
    from astropy.wcs import WCS
    from reproject import reproject_interp
    from .clean import flag_bits
    count = np.zeros(shape, int)
    for p in paths:
        with fits.open(p) as h:
            flags = h["FLAGS"].data.astype(np.int64)
            bits = flag_bits(h["FLAGS"].header)
            wcs = WCS(h["IMAGE"].header)
        sat = np.zeros(flags.shape, bool)
        for name in SAT_FLAGS:
            if name in bits:
                sat |= (flags & (1 << bits[name])) != 0
        if sat.any():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                on_grid = reproject_interp((sat.astype(float), wcs), grid_wcs, shape_out=shape,
                                           return_footprint=False)
            count += np.nan_to_num(on_grid) > 0.25
    return count >= min_frames


def flux_centroid(img, x, y, r, iterations=2):
    """Flux-weighted centroid (x, y) of the positive pixels within r of (x, y), re-centred
    `iterations` times. NaN when there is no positive flux there."""
    yy, xx = np.mgrid[:img.shape[0], :img.shape[1]]
    for _ in range(iterations):
        w = ((xx - x) ** 2 + (yy - y) ** 2 <= r * r) & np.isfinite(img)
        v = np.where(w, np.clip(np.nan_to_num(img), 0, None), 0.0)
        total = v.sum()
        if total <= 0:
            return np.nan, np.nan
        x, y = float((v * xx).sum() / total), float((v * yy).sum() / total)
    return x, y


def saturated_stars(sat_a, sat_b, img_a, img_b):
    """Saturated cores in either visit of a pair -> list of dicts: x, y (centre), r_core (radius of
    a circle of the same area), r_ring (out to where its wings and rings reach), shift_px (how far
    its flux centroid moved from visit a to b), moving (shift_px > SAT_MOVE_PX).
    The centroid is measured on the two stacks around the core (radius r_core + 4 px)."""
    from scipy import ndimage
    lab, n = ndimage.label(sat_a | sat_b)
    out = []
    for k in range(1, n + 1):
        blob = lab == k
        area = int(blob.sum())
        if area < SAT_MIN_AREA_PX:
            continue
        cy, cx = ndimage.center_of_mass(blob)
        r_core = float(np.sqrt(area / np.pi))
        xa, ya = flux_centroid(img_a, cx, cy, r_core + 4)
        xb, yb = flux_centroid(img_b, cx, cy, r_core + 4)
        shift = float(np.hypot(xb - xa, yb - ya)) if np.isfinite(xa + xb) else np.nan
        out.append({"x": float(cx), "y": float(cy), "area_px": area, "r_core": r_core,
                    "r_ring": SAT_RING_FACTOR * r_core + SAT_PAD_PX, "shift_px": shift,
                    "moving": bool(np.isfinite(shift) and shift > SAT_MOVE_PX),
                    "xa": xa, "ya": ya, "xb": xb, "yb": yb})
    return out


def _coverage_pair(epochs, a, b):
    cov_b = epochs[b]["coverage"]
    cov_a = epochs[a]["coverage"] if a >= 0 else np.min([e["coverage"] for i, e in enumerate(epochs) if i != b], axis=0)
    return np.minimum(cov_a, cov_b)


def _sat_pair(sat_maps, a, b):
    if sat_maps is None:
        return None, None
    sat_b = sat_maps[b]
    sat_a = sat_maps[a] if a >= 0 else np.any([m for i, m in enumerate(sat_maps) if i != b], axis=0)
    return sat_a, sat_b


def apply_cuts(residuals, epochs, sat_maps=None, min_frames=MIN_FRAMES, edge_px=EDGE_PX, min_change=MIN_CHANGE):
    """Residuals (find_residuals) -> (same table with new columns, summary dict).
    New columns:
      cut        '' (kept) or the first cut it failed, in the order of CUTS:
                 'low coverage': fewer than min_frames frames under it in either visit (few-frames
                     visits fail everywhere: their stacks cannot reject a bad frame);
                 'edge': within edge_px of the area both visits cover with min_frames frames;
                 'saturated star wings': within r_ring of a saturated core that did not move, or
                     in the wings (beyond r_core + shift + 2 px) of one that moved;
                 'small change': |peak| below min_change x the brightest pixel within 2 px in either
                     stack (see MIN_CHANGE);
      change     that ratio, |peak| / brightest stack pixel nearby;
      coverage   frames under it (the smaller of the two visits, smallest of the 3x3 around it);
      saturated  inside the core of a saturated star that moved between the visits (kept);
      sat_shift_px  that star's centroid shift (NaN if not saturated); sat_xa, sat_ya, sat_xb,
                 sat_yb its flux centroid in visit a and in visit b (grid pixels);
      release_boundary  the two visits come from different data releases (calibration differs by
                 a few percent between DR1 and QR3): flagged, not cut;
      seen_in, seen_possible  in how many OTHER images a kept residual lies within REPEAT_PX of this
                 one, out of how many cover this place with min_frames frames (kept rows only).
    sat_maps: one saturation_map per epoch, or None (no saturation cut: every row gets
    saturated False and the summary says the cut was not made).
    summary: input count, removed per cut, kept, pairs whose visits have few frames."""
    from scipy import ndimage
    t = residuals.copy()
    n = len(t)
    cut = [""] * n
    cover = np.zeros(n, int)
    saturated = np.zeros(n, bool)
    sat_shift = np.full(n, np.nan)
    sat_pos = np.full((n, 4), np.nan)                     # moving saturated star: xa, ya, xb, yb
    boundary = np.zeros(n, bool)
    change = np.full(n, np.nan)
    few_pairs = []
    good_cache = {}
    for label in sorted(set(t["pair"]), key=lambda p: list(t["pair"]).index(p)):
        rows = np.where(t["pair"] == label)[0]
        a, b = int(t["visit_a"][rows[0]]), int(t["visit_b"][rows[0]])
        cov = _coverage_pair(epochs, a, b)
        good = cov >= min_frames
        inner = ndimage.binary_erosion(good, iterations=edge_px, border_value=0) if edge_px > 0 else good
        good_cache[label] = good
        n_a = epochs[a].get("n_min", min_frames) if a >= 0 else min(e.get("n_min", min_frames) for i, e in enumerate(epochs) if i != b)
        if min(n_a, epochs[b].get("n_min", min_frames)) < min_frames:
            few_pairs.append(label)
        rel_a = epochs[a].get("releases", "") if a >= 0 else ",".join(sorted({e.get("releases", "") for i, e in enumerate(epochs) if i != b}))
        rel_b = epochs[b].get("releases", "")
        sat_a, sat_b = _sat_pair(sat_maps, a, b)
        img_a = epochs[a]["image"] if a >= 0 else None
        stars = saturated_stars(sat_a, sat_b, img_a if img_a is not None else epochs[b]["image"] * 0,
                                epochs[b]["image"]) if sat_a is not None else []
        ny, nx = cov.shape
        stacks = [epochs[b]["image"]] + ([epochs[a]["image"]] if a >= 0 else
                                         [e["image"] for j, e in enumerate(epochs) if j != b])
        for i in rows:
            x, y = float(t["x"][i]), float(t["y"][i])
            ix, iy = int(np.clip(round(x), 0, nx - 1)), int(np.clip(round(y), 0, ny - 1))
            cover[i] = int(cov[max(iy - 1, 0):iy + 2, max(ix - 1, 0):ix + 2].min())
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                star = max(np.nanmax(im[max(iy - 2, 0):iy + 3, max(ix - 2, 0):ix + 3]) for im in stacks)
            change[i] = abs(float(t["peak"][i])) / star if star > 0 else np.inf
            boundary[i] = bool(rel_a and rel_b and rel_a != rel_b)
            if cover[i] < min_frames:
                cut[i] = "low coverage"
                continue
            if not inner[iy, ix]:
                cut[i] = "edge"
                continue
            for s in stars:
                d = np.hypot(x - s["x"], y - s["y"])
                if d > s["r_ring"]:
                    continue
                if s["moving"] and d <= s["r_core"] + s["shift_px"] + 2:
                    saturated[i] = True
                    sat_shift[i] = s["shift_px"]
                    sat_pos[i] = (s["xa"], s["ya"], s["xb"], s["yb"])
                else:
                    cut[i] = "saturated star wings"
                break
            if not cut[i] and not saturated[i] and change[i] < min_change:
                cut[i] = "small change"
    t["cut"] = cut
    t["change"] = change
    t["coverage"] = cover
    t["saturated"] = saturated
    t["sat_shift_px"] = sat_shift
    for k, name in enumerate(("sat_xa", "sat_ya", "sat_xb", "sat_yb")):
        t[name] = sat_pos[:, k]
    t["release_boundary"] = boundary
    # seen in other images (kept rows only)
    kept = np.array([c == "" for c in cut], bool)
    seen = np.zeros(n, int)
    possible = np.zeros(n, int)
    labels = sorted(good_cache, key=lambda p: list(t["pair"]).index(p))
    for i in np.where(kept)[0]:
        x, y = float(t["x"][i]), float(t["y"][i])
        for other in labels:
            if other == t["pair"][i]:
                continue
            g = good_cache[other]
            if g[int(np.clip(round(y), 0, g.shape[0] - 1)), int(np.clip(round(x), 0, g.shape[1] - 1))]:
                possible[i] += 1
                o = kept & (t["pair"] == other)
                if np.any(np.hypot(np.asarray(t["x"][o]) - x, np.asarray(t["y"][o]) - y) <= REPEAT_PX):
                    seen[i] += 1
    t["seen_in"] = seen
    t["seen_possible"] = possible
    summary = {"residuals": n, **{c: int(sum(x == c for x in cut)) for c in CUTS},
               "kept": int(kept.sum()), "few_frames_pairs": few_pairs,
               "saturation_cut": sat_maps is not None,
               "release_boundary_kept": int((boundary & kept).sum()),
               "seen_in_another_kept": int(((seen > 0) & kept).sum()),
               "could_repeat_kept": int(((possible > 0) & kept).sum())}
    return t, summary


# ------------------------------------------------------------------ 3. classify and cross-match
PIXSCALE_ARCSEC = 3.0   # the stacks' grid (make_epochs default)
MAX_PM_ARCSEC_YR = 15.0 # dipole lobes may be at most MAX_PM x baseline + 2 x PSF apart (the fastest
                        #   known stars move ~10"/yr; a blended dipole's lobes are ~1 PSF apart
                        #   however small the motion)
PSF_FWHM_PX = 2.0       # SPHEREx PSF on the 3" grid, roughly (6.15" pixels)
LOBE_RATIO = 4.0        # the two lobes of a dipole differ in flux by at most this factor
MATCH_ARCSEC = 3.0      # catalogue match radius, as in the overlay verdicts. Real residuals in the
                        #   Barnard's Star field sit 0.3-1.6" from their star; at 6" half of all
                        #   random positions there would "match" a Gaia source (chance_match)
CHANCE_NOTE = 0.05      # a match by chance more likely than this is mentioned in the verdict
PM_AGREE = (1.0, 0.3)   # implied and catalogue motion agree within max(1"/yr, 30%)
ASTEROID_MATCH_ARCSEC = 10.0   # around the asteroid's path during the visit

LABELS = {
    "known star": "A Gaia DR3 source lies within {r}″ (a known star).",
    "known infrared source": "A CatWISE2020 source lies within {r}″, none in Gaia (a known object that "
                             "is faint or cold in visible light).",
    "known asteroid": "A known asteroid or comet (SkyBoT) passes within {ra}″ during the visit.",
    "unexplained": "No Gaia DR3, CatWISE2020 or SkyBoT object within {r}″. This is not a detection: "
                   "most such residuals are artefacts. Look at the pictures.",
}

CANDIDATE_COLUMNS = ["pair", "visit_a", "visit_b", "date_a", "date_b", "type", "ra", "dec", "x", "y",
                     "significance", "sign", "shift_arcsec", "pm_arcsec_yr", "pm_pa_deg", "change",
                     "saturated", "release_boundary", "seen_in", "seen_possible", "n_residuals"]


def _years(mjd_a, mjd_b):
    return (mjd_b - mjd_a) / 365.25


def motion(ep_a, ep_b, x, y, r, pixscale_arcsec=PIXSCALE_ARCSEC):
    """Centroid shift of the source near (x, y) from stack a to stack b -> (xa, ya, xb, yb,
    shift_arcsec, pm_arcsec_yr, position angle deg east of north). The flux-weighted centroid is
    measured on each stack within r pixels (a blended dipole's lobes are about one PSF apart
    whatever the motion, so the lobe separation is no measure of it)."""
    xa, ya = flux_centroid(ep_a["image"], x, y, r)
    xb, yb = flux_centroid(ep_b["image"], x, y, r)
    if not np.isfinite(xa + xb):
        return xa, ya, xb, yb, np.nan, np.nan, np.nan
    dx, dy = xb - xa, yb - ya                 # north-up grid with cdelt1 < 0: x grows to the west
    shift = float(np.hypot(dx, dy) * pixscale_arcsec)
    years = _years(ep_a["mjd"], ep_b["mjd"])
    pa = float(np.degrees(np.arctan2(-dx, dy)) % 360)    # east = -x on a north-up grid
    return xa, ya, xb, yb, shift, shift / years if years > 0 else np.nan, pa


def classify(cut_table, epochs, max_pm=MAX_PM_ARCSEC_YR, pixscale_arcsec=PIXSCALE_ARCSEC):
    """Kept residuals (apply_cuts, cut == '') -> Table of candidates (CANDIDATE_COLUMNS), one per
    object per image:
      mover     a dipole: a negative residual (where it was in visit a) and a positive one (where it
                is in visit b) within max_pm x baseline + 2 PSF of each other, fluxes within
                LOBE_RATIO, whose measured motion is at most max_pm; or the residuals in the core of a saturated star that moved. ra, dec, x,
                y = its centroid in visit b; shift and pm from the centroid shift (motion());
      variable  an unpaired residual at a place where another image also has one (seen_in > 0);
      single    any other unpaired residual: present in one visit only (an asteroid, a flare, an
                artefact), or a change seen once.
    For minus_mean images (visit_a = -1) no dipoles are formed (no single earlier visit)."""
    k = cut_table[cut_table["cut"] == ""]
    out = []
    for label in sorted(set(k["pair"]), key=lambda p: list(k["pair"]).index(p)):
        s = k[k["pair"] == label]
        a, b = int(s["visit_a"][0]), int(s["visit_b"][0])
        used = set()
        if a >= 0:
            years = _years(epochs[a]["mjd"], epochs[b]["mjd"])
            max_sep = max_pm * years / pixscale_arcsec + 2 * PSF_FWHM_PX
            # saturated movers: all residuals of one moving core -> one candidate
            sat = [i for i in range(len(s)) if s["saturated"][i]]
            groups = {}
            for i in sat:
                groups.setdefault((round(float(s["sat_xb"][i]), 3), round(float(s["sat_yb"][i]), 3)), []).append(i)
            for key in sorted(groups):
                idx = groups[key]
                i0 = max(idx, key=lambda i: s["significance"][i])
                xa, ya, xb, yb = (float(s[c][i0]) for c in ("sat_xa", "sat_ya", "sat_xb", "sat_yb"))
                shift = float(np.hypot(xb - xa, yb - ya) * pixscale_arcsec)
                out.append(_candidate(s, i0, epochs, "mover", xb, yb, shift, shift / years,
                                      float(np.degrees(np.arctan2(-(xb - xa), yb - ya)) % 360), len(idx)))
                used |= set(idx)
            pos = sorted([i for i in range(len(s)) if s["sign"][i] > 0 and i not in used],
                         key=lambda i: (-s["significance"][i], i))
            neg = [i for i in range(len(s)) if s["sign"][i] < 0 and i not in used]
            for i in pos:
                options = []
                for j in neg:
                    if j in used:
                        continue
                    d = float(np.hypot(s["x"][i] - s["x"][j], s["y"][i] - s["y"][j]))
                    ratio = abs(s["flux"][i] / s["flux"][j]) if s["flux"][j] else np.inf
                    if d <= max_sep and 1 / LOBE_RATIO <= ratio <= LOBE_RATIO:
                        options.append((d, j))
                best = None
                for d, j in sorted(options):              # nearest first; the motion must be plausible too
                    mx, my = (s["x"][i] + s["x"][j]) / 2, (s["y"][i] + s["y"][j]) / 2
                    meas = motion(epochs[a], epochs[b], mx, my, d / 2 + 2 * PSF_FWHM_PX, pixscale_arcsec)
                    if np.isfinite(meas[5]) and meas[5] <= max_pm:
                        best, (xa, ya, xb, yb, shift, pm, pa) = j, meas
                        break
                if best is None:
                    continue
                cx, cy = (xb, yb) if np.isfinite(xb) else (float(s["x"][i]), float(s["y"][i]))
                out.append(_candidate(s, i, epochs, "mover", cx, cy, shift, pm, pa, 2,
                                      significance=max(s["significance"][i], s["significance"][best])))
                used |= {i, best}
        for i in range(len(s)):
            if i in used:
                continue
            kind = "variable" if s["seen_in"][i] > 0 else "single"
            out.append(_candidate(s, i, epochs, kind, float(s["x"][i]), float(s["y"][i]), np.nan, np.nan, np.nan, 1))
    t = Table(rows=out, names=CANDIDATE_COLUMNS) if out else Table(
        names=CANDIDATE_COLUMNS, dtype=[str, int, int, str, str, str] + [float] * 5 + [int] + [float] * 4
        + [bool, bool, int, int, int])
    if len(t):
        for c in ("x", "y"):
            t[c] = np.asarray(t[c], float)
        wcs = epochs[0]["wcs"]
        sky = wcs.pixel_to_world(np.asarray(t["x"]), np.asarray(t["y"]))
        t["ra"], t["dec"] = sky.ra.deg, sky.dec.deg
    return t


def _candidate(s, i, epochs, kind, x, y, shift, pm, pa, n_res, significance=None):
    return [s["pair"][i], int(s["visit_a"][i]), int(s["visit_b"][i]), s["date_a"][i], s["date_b"][i], kind,
            np.nan, np.nan, float(x), float(y),
            float(s["significance"][i] if significance is None else significance),
            0 if kind == "mover" else int(s["sign"][i]), float(shift), float(pm), float(pa),
            float(s["change"][i]), bool(s["saturated"][i]), bool(s["release_boundary"][i]),
            int(s["seen_in"][i]), int(s["seen_possible"][i]), int(n_res)]


def _epoch_of(c, epochs):
    """The visit a candidate's position refers to: visit b (where it is now), or visit a for a
    negative single (something that was there in a and is gone in b)."""
    if c["type"] == "single" and c["sign"] < 0 and c["visit_a"] >= 0:
        return epochs[int(c["visit_a"])]
    return epochs[int(c["visit_b"])]


def crossmatch(cands, epochs, gaia=True, wise=True, asteroids=True, radius_deg=0.15,
               match_arcsec=MATCH_ARCSEC, progress=None):
    """Candidates (classify) -> (same table with catalogue columns and a label, notes).
    Each candidate is matched at the date of the visit its position refers to (_epoch_of):
      Gaia DR3 (spherex.gaia, propagated with its proper motion), CatWISE2020 (spherex.wise,
      propagated with its motion), SkyBoT (spherex.asteroids) at the first and the last frame of the
      visit, a candidate within ASTEROID_MATCH_ARCSEC of the straight path between the two.
    New columns: gaia_sep_arcsec, gaia_source_id, gaia_g, gaia_pm_arcsec_yr, wise_sep_arcsec,
    wise_name, asteroid, asteroid_sep_arcsec, label (LABELS keys), chance_match (probability that a
    random position in this field has a source of the label's catalogue that close: 1 - exp(-density
    x area), from the number of catalogue sources in the circle), verdict (the sentence; it says
    when chance_match >= CHANCE_NOTE, and for a mover matched to a Gaia star whether the star's
    catalogue motion agrees with the implied one, within PM_AGREE).
    notes: catalogues that failed (then no candidate can get that label), counts per label.
    The catalogues are asked once per visit, for a circle of radius_deg around the grid centre
    (0.15 deg covers a 10' view; the same circle as the cached demo cones)."""
    from astropy.coordinates import SkyCoord
    from astropy.time import Time
    import astropy.units as u
    from .progress import report, SEARCHING
    t = cands.copy()
    n = len(t)
    cols = {"gaia_sep_arcsec": np.full(n, np.nan), "gaia_source_id": [""] * n, "gaia_g": np.full(n, np.nan),
            "gaia_pm_arcsec_yr": np.full(n, np.nan), "wise_sep_arcsec": np.full(n, np.nan),
            "wise_name": [""] * n, "asteroid": [""] * n, "asteroid_sep_arcsec": np.full(n, np.nan)}
    notes = {"failed": [], "asked": [], "chance_match": {}}
    if not n:
        for c, v in cols.items():
            t[c] = v
        t["label"], t["verdict"] = [], []
        return t, notes
    shape = epochs[0]["image"].shape
    center = epochs[0]["wcs"].pixel_to_world(shape[1] / 2, shape[0] / 2)
    visits = []
    for c in t:
        ep = _epoch_of(c, epochs)
        if not any(ep is v for v in visits):
            visits.append(ep)
    jobs = len(visits) * (int(bool(gaia)) + int(bool(wise)) + 2 * int(bool(asteroids)))
    done = 0
    report(progress, SEARCHING, 0, jobs)
    pos = SkyCoord(np.asarray(t["ra"]) * u.deg, np.asarray(t["dec"]) * u.deg)
    for ep in visits:
        rows = np.array([_epoch_of(c, epochs) is ep for c in t])
        when = Time(ep["mjd"], format="mjd")
        here = pos[rows]
        idx = np.where(rows)[0]
        for name, wanted in (("gaia", gaia), ("wise", wise)):
            if not wanted:
                continue
            try:
                if name == "gaia":
                    from .gaia import gaia_overlay
                    stars = gaia_overlay(center, radius_deg, when)
                else:
                    from .wise import wise_overlay
                    stars = wise_overlay(center, radius_deg, when)
                if name not in notes["asked"]:
                    notes["asked"].append(name)
                    density = len(stars) / (np.pi * (radius_deg * 3600) ** 2)      # per square arcsec
                    notes["chance_match"][name] = float(1 - np.exp(-density * np.pi * match_arcsec ** 2))
                if len(stars):
                    cat = SkyCoord(np.asarray(stars["ra_t"]) * u.deg, np.asarray(stars["dec_t"]) * u.deg)
                    j, sep, _ = here.match_to_catalog_sky(cat)
                    for k, jj, ss in zip(idx, j, sep.arcsec):
                        if name == "gaia":
                            cols["gaia_sep_arcsec"][k] = ss
                            cols["gaia_source_id"][k] = str(stars["source_id"][jj])
                            cols["gaia_g"][k] = float(stars["phot_g_mean_mag"][jj])
                            cols["gaia_pm_arcsec_yr"][k] = float(stars["pm_total"][jj]) / 1000
                        else:
                            cols["wise_sep_arcsec"][k] = ss
                            cols["wise_name"][k] = str(stars["source_name"][jj])
            except Exception as e:
                msg = f"{name}: {type(e).__name__}: {str(e)[:80]}"
                if msg not in notes["failed"]:
                    notes["failed"].append(msg)
            done += 1
            report(progress, SEARCHING, done, jobs)
        if asteroids:
            try:
                from .asteroids import known_asteroids
                fov_r = float(np.hypot(*shape) / 2 * PIXSCALE_ARCSEC / 3600) * 1.2
                ends = []
                for m in (ep.get("first_mjd", ep["mjd"]), ep.get("last_mjd", ep["mjd"])):
                    ends.append(known_asteroids(center, fov_r, Time(m, format="mjd")))
                    done += 1
                    report(progress, SEARCHING, done, jobs)
                if "asteroids" not in notes["asked"]:
                    notes["asked"].append("asteroids")
                first, last = ends
                for r in first:
                    other = last[last["name"] == r["name"]]
                    p0 = SkyCoord(r["ra"] * u.deg, r["dec"] * u.deg)
                    p1 = SkyCoord(other["ra"][0] * u.deg, other["dec"][0] * u.deg) if len(other) else p0
                    for k, c in zip(idx, here):
                        d = _sep_to_segment(c, p0, p1)
                        if d < ASTEROID_MATCH_ARCSEC and not (cols["asteroid_sep_arcsec"][k] <= d):
                            cols["asteroid"][k] = str(r["name"])
                            cols["asteroid_sep_arcsec"][k] = d
            except Exception as e:
                msg = f"asteroids: {type(e).__name__}: {str(e)[:80]}"
                if msg not in notes["failed"]:
                    notes["failed"].append(msg)
                done = min(jobs, done + 2)
                report(progress, SEARCHING, done, jobs)
    for c, v in cols.items():
        t[c] = v
    labels, verdicts, chance = [], [], []
    for k in range(n):
        p = np.nan
        if cols["gaia_sep_arcsec"][k] <= match_arcsec:
            lab, p = "known star", notes["chance_match"].get("gaia", np.nan)
        elif cols["wise_sep_arcsec"][k] <= match_arcsec:
            lab, p = "known infrared source", notes["chance_match"].get("wise", np.nan)
        elif cols["asteroid_sep_arcsec"][k] <= ASTEROID_MATCH_ARCSEC:
            lab = "known asteroid"
        else:
            lab = "unexplained"
        text = LABELS[lab].format(r=f"{match_arcsec:g}", ra=f"{ASTEROID_MATCH_ARCSEC:g}")
        agrees = None
        if lab == "known star" and t["type"][k] == "mover":
            implied, cat = float(t["pm_arcsec_yr"][k]), cols["gaia_pm_arcsec_yr"][k]
            if np.isfinite(implied) and np.isfinite(cat):
                agrees = abs(implied - cat) <= max(PM_AGREE[0], PM_AGREE[1] * cat)
                if agrees:
                    text += f" Its catalogue motion, {cat:.2f}″/yr, agrees with the implied {implied:.2f}″/yr."
                else:
                    text += (f" Its catalogue motion is {cat:.2f}″/yr, not the implied {implied:.2f}″/yr: the "
                             "dipole is not this star's motion (most likely the star looks different in "
                             "the two visits).")
        if np.isfinite(p) and p >= CHANCE_NOTE and not agrees:     # an agreeing motion is no coincidence
            text += (f" In this field a random position has a {p:.0%} chance of a source that close, so "
                     "the match may be a coincidence.")
        labels.append(lab)
        verdicts.append(text)
        chance.append(p)
    t["label"] = labels
    t["chance_match"] = chance
    t["verdict"] = verdicts
    notes["labels"] = {lab: labels.count(lab) for lab in LABELS}
    return t, notes


def _sep_to_segment(c, p0, p1):
    """Angular distance (arcsec) of SkyCoord c from the great-circle segment p0-p1 (small angles)."""
    import astropy.units as u
    off = p0.spherical_offsets_to(c)
    seg = p0.spherical_offsets_to(p1)
    v = np.array([off[0].to_value(u.arcsec), off[1].to_value(u.arcsec)])
    s = np.array([seg[0].to_value(u.arcsec), seg[1].to_value(u.arcsec)])
    L2 = float(s @ s)
    f = 0.0 if L2 == 0 else float(np.clip((v @ s) / L2, 0, 1))
    return float(np.hypot(*(v - f * s)))
