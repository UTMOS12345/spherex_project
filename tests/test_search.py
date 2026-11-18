"""Blind search (spherex.search) on synthetic visits: known positions, no network, no cache."""
import numpy as np
import pytest
from astropy.coordinates import SkyCoord
import astropy.units as u

from spherex import search
from spherex.epochs import make_grid

N = 120


def gauss(x0, y0, amp, sigma=1.3):
    y, x = np.mgrid[:N, :N]
    return amp * np.exp(-((x - x0) ** 2 + (y - y0) ** 2) / (2 * sigma ** 2))


def visits(sources, n_visits=3, noise=0.01, seed=1, coverage=10, step_days=180.0):
    """sources: list of callables visit_index -> image. Returns make_epochs-like dicts."""
    wcs, shape = make_grid(SkyCoord(150 * u.deg, 2 * u.deg), N * 3 / 60, 3.0)
    rng = np.random.default_rng(seed)
    eps = []
    for i in range(n_visits):
        img = rng.normal(0, noise, shape)
        for s in sources:
            img = img + s(i)
        mjd = 61000.0 + step_days * i
        eps.append({"epoch": i, "image": img, "coverage": np.full(shape, coverage), "wcs": wcs,
                    "mjd": mjd, "date": f"visit{i}", "n_min": coverage, "n_frames": coverage,
                    "releases": "DR1", "detector": "D2"})
    return eps


def test_dipole_found_as_one_positive_and_one_negative():
    star = lambda i: gauss(60 + 3 * i, 60, 5.0)          # moves 3 px per visit
    t = search.find_residuals(visits([star], n_visits=2))
    assert set(t["sign"]) == {1, -1}
    pos, neg = t[t["sign"] > 0][0], t[t["sign"] < 0][0]
    assert pos["x"] > neg["x"] and abs(pos["y"] - 60) < 1 and abs(neg["y"] - 60) < 1
    assert pos["significance"] > 50 and pos["pair"] == "0-1"


def test_noise_only_gives_almost_nothing():
    t = search.find_residuals(visits([], n_visits=3))
    assert len(t) <= 1                                     # 5 sigma, 5 px: noise rarely passes


def test_pairs_and_minus_mean_images():
    eps = visits([], n_visits=4)
    assert [x[0] for x in search.residual_images(eps, "pairs")] == ["0-1", "1-2", "2-3"]
    assert len(search.residual_images(eps, "pairs", "all")) == 6
    assert [x[0] for x in search.residual_images(eps, "minus_mean")] == ["0-mean", "1-mean", "2-mean", "3-mean"]
    with pytest.raises(ValueError):
        search.residual_images(eps, "pairs", "nearest")


def test_same_input_same_table():
    eps = visits([lambda i: gauss(40 + 2 * i, 70, 2.0), lambda i: gauss(90, 30, 1.0 + i)])
    a, b = search.find_residuals(eps), search.find_residuals(eps)
    assert len(a) > 0 and all((a[c] == b[c]).all() for c in a.colnames)


# ------------------------------------------------------------------ 2. artefact cuts
def _cut_of(t, x, y, r=3.0):
    """cut of the residual nearest (x, y), within r pixels; None when there is none."""
    d = np.hypot(np.asarray(t["x"]) - x, np.asarray(t["y"]) - y)
    return None if not len(t) or d.min() > r else str(t["cut"][int(np.argmin(d))])


def test_low_coverage_and_edge_cuts():
    eps = visits([lambda i: gauss(30, 60, 3.0 * i), lambda i: gauss(60, 60, 3.0 * i),
                  lambda i: gauss(117, 60, 3.0 * i)], n_visits=2)
    eps[1]["coverage"] = eps[1]["coverage"].copy()
    eps[1]["coverage"][:, :40] = 2                       # few frames on the left
    t, summary = search.apply_cuts(search.find_residuals(eps), eps)
    assert _cut_of(t, 30, 60) == "low coverage"
    assert _cut_of(t, 60, 60) == ""                       # a new source: kept
    assert _cut_of(t, 117, 60) == "edge"                  # 2 px from the border
    assert summary["low coverage"] >= 1 and summary["edge"] >= 1 and not summary["saturation_cut"]


def test_static_saturated_star_rings_are_cut_but_a_moving_one_is_kept():
    ring = lambda i: (0.5 if i else -0.5) * (gauss(30, 30, 1.0, 6) - gauss(30, 30, 1.0, 4))   # wing residual
    static = lambda i: gauss(30, 30, 50.0, 2.5)
    mover = lambda i: gauss(85 + 3 * i, 80, 50.0, 2.5)
    eps = visits([static, ring, mover], n_visits=2)
    sat = []
    for i in range(2):
        m = np.zeros((N, N), bool)
        m[27:34, 27:34] = True                            # the static core, both visits
        m[77:84, 82 + 3 * i:89 + 3 * i] = True            # the moving core
        sat.append(m)
    stars = search.saturated_stars(sat[0], sat[1], eps[0]["image"], eps[1]["image"])
    assert sorted(s["moving"] for s in stars) == [False, True]
    assert [round(s["shift_px"]) for s in stars if s["moving"]] == [3]
    t, summary = search.apply_cuts(search.find_residuals(eps), eps, sat)
    near_static = t[np.hypot(np.asarray(t["x"]) - 30, np.asarray(t["y"]) - 30) < 25]
    assert len(near_static) and set(near_static["cut"]) == {"saturated star wings"}
    mov = t[np.hypot(np.asarray(t["x"]) - 86.5, np.asarray(t["y"]) - 80) < 6]
    assert set(mov["sign"]) == {1, -1} and set(mov["cut"]) == {""} and mov["saturated"].all()


def test_small_change_cut_and_release_flag():
    bright = lambda i: gauss(40, 40, 10.0 * (1 + 0.05 * i))   # 5 % brighter: calibration-like
    flare = lambda i: gauss(80, 80, 1.0 + 2.0 * i)             # 3x brighter: a real change
    eps = visits([bright, flare], n_visits=2)
    eps[1]["releases"] = "QR3"
    t, _ = search.apply_cuts(search.find_residuals(eps), eps)
    assert _cut_of(t, 40, 40) == "small change"
    assert _cut_of(t, 80, 80) == ""
    assert t["release_boundary"].all()


def test_seen_in_other_pairs():
    var = lambda i: gauss(60, 60, [1.0, 3.0, 1.0][i])          # up, then down again
    t, summary = search.apply_cuts(search.find_residuals(visits([var], n_visits=3)), visits([var], n_visits=3))
    k = t[t["cut"] == ""]
    assert len(k) == 2 and set(k["seen_in"]) == {1} and set(k["seen_possible"]) == {1}
    assert summary["seen_in_another_kept"] == 2
