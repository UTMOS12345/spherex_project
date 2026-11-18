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
