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
    assert pos["peak_to_noise"] > 50 and pos["pair"] == "0-1"


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


# ------------------------------------------------------------------ 3. classify and cross-match
from astropy.table import Table


def _classified(sources, n_visits=2, step_days=180.0, **kw):
    eps = visits(sources, n_visits=n_visits, step_days=step_days, **kw)
    t, _ = search.apply_cuts(search.find_residuals(eps), eps)
    return eps, search.classify(t, eps)


def test_dipole_pairing_and_implied_motion():
    # 3 px per 180 days on the 3" grid = 9" / 0.493 yr = 18.3"/yr: above MAX_PM, so not paired
    eps, c = _classified([lambda i: gauss(60 + 3 * i, 60, 4.0)])
    assert "mover" not in set(c["type"])
    # 1.5 px per 180 days = 9.1"/yr toward -x (east): paired, motion measured from the centroids
    eps, c = _classified([lambda i: gauss(60 - 1.5 * i, 60, 4.0)])
    m = c[c["type"] == "mover"]
    assert len(m) == 1 and m["n_residuals"][0] == 2
    assert abs(m["pm_arcsec_yr"][0] - 1.5 * 3 / (180 / 365.25)) < 0.5
    assert abs(m["pm_pa_deg"][0] - 90) < 10                       # east of north
    assert abs(m["x"][0] - 58.5) < 0.3                            # position in the later visit


def test_variable_vs_single():
    var = lambda i: gauss(40, 40, [1.0, 3.0, 1.0][i])             # changes twice at one place
    new = lambda i: gauss(80, 80, 2.0 if i == 2 else 0.0)         # appears once
    eps, c = _classified([var, new], n_visits=3)
    kinds = {(round(x), round(y)): k for x, y, k in zip(c["x"], c["y"], c["type"])}
    assert kinds[(40, 40)] == "variable" and kinds[(80, 80)] == "single"


def _fake_catalogues(monkeypatch, gaia_rows, wise_rows=(), asteroid_rows=None):
    from spherex import gaia, wise, asteroids
    def g(center, radius, t):
        return Table(rows=list(gaia_rows) or None, names=["source_id", "ra_t", "dec_t", "phot_g_mean_mag", "pm_total"],
                     dtype=[str, float, float, float, float])
    def w(center, radius, t):
        return Table(rows=list(wise_rows) or None, names=["source_name", "ra_t", "dec_t"], dtype=[str, float, float])
    def a(center, radius, t):
        if asteroid_rows is None:
            raise OSError("SkyBoT down")
        return Table(rows=list(asteroid_rows) or None, names=["name", "type", "ra", "dec", "v_mag"],
                     dtype=[str, str, float, float, float])
    monkeypatch.setattr(gaia, "gaia_overlay", g)
    monkeypatch.setattr(wise, "wise_overlay", w)
    monkeypatch.setattr(asteroids, "known_asteroids", a)


def test_crossmatch_labels_and_wording(monkeypatch):
    eps, c = _classified([lambda i: gauss(60 - 1.5 * i, 60, 4.0),          # a mover
                          lambda i: gauss(30, 90, 2.0 if i else 0.0),       # appears: unexplained
                          lambda i: gauss(90, 30, 2.0 if i else 0.0)])      # appears at a WISE source
    wcs = eps[0]["wcs"]
    m = c[c["type"] == "mover"][0]
    star = wcs.pixel_to_world(m["x"], m["y"])
    ir = wcs.pixel_to_world(90, 30)
    _fake_catalogues(monkeypatch, [("1", star.ra.deg, star.dec.deg, 9.0, 2.0)],      # moves 2"/yr, not 9
                     [("J1", ir.ra.deg, ir.dec.deg)], asteroid_rows=None)
    t, notes = search.crossmatch(c, eps)
    lab = {(round(x), round(y)): (l, v) for x, y, l, v in zip(t["x"], t["y"], t["label"], t["verdict"])}
    mover_label, mover_text = lab[(round(m["x"]), round(m["y"]))]
    assert mover_label == "known star" and "not the implied" in mover_text
    assert lab[(90, 30)][0] == "known infrared source"
    assert lab[(30, 90)][0] == "unexplained" and "This is not a detection" in lab[(30, 90)][1]
    assert any(f.startswith("asteroids: OSError") for f in notes["failed"])
    assert notes["labels"]["known asteroid"] == 0


def test_chance_match_is_reported_in_crowded_fields(monkeypatch):
    eps, c = _classified([lambda i: gauss(30, 90, 2.0 if i else 0.0)])
    wcs = eps[0]["wcs"]
    p = wcs.pixel_to_world(c["x"][0], c["y"][0])
    rng = np.random.default_rng(0)                               # 20000 stars in the 0.15 deg circle
    crowd = [(str(k), p.ra.deg + rng.uniform(-0.15, 0.15), p.dec.deg + rng.uniform(-0.15, 0.15), 20.0, 0.0)
             for k in range(20000)] + [("near", p.ra.deg, p.dec.deg + 1 / 3600, 20.0, 0.0)]
    _fake_catalogues(monkeypatch, crowd, asteroid_rows=[])
    t, notes = search.crossmatch(c, eps)
    assert t["label"][0] == "known star" and notes["chance_match"]["gaia"] > 0.3
    assert "may be a coincidence" in t["verdict"][0]


def test_asteroid_on_its_path(monkeypatch):
    eps, c = _classified([lambda i: gauss(30, 90, 2.0 if i else 0.0)])
    wcs = eps[0]["wcs"]
    p0, p1 = wcs.pixel_to_world(20, 90), wcs.pixel_to_world(40, 90)   # passes through (30, 90)
    calls = []
    from spherex import gaia, wise, asteroids
    _fake_catalogues(monkeypatch, [], asteroid_rows=[])
    def a(center, radius, t):
        calls.append(t)
        q = p0 if len(calls) % 2 else p1
        return Table(rows=[("(1) Ceres", "MB", q.ra.deg, q.dec.deg, 9.0)], names=["name", "type", "ra", "dec", "v_mag"])
    monkeypatch.setattr(asteroids, "known_asteroids", a)
    t, notes = search.crossmatch(c, eps)
    assert t["label"][0] == "known asteroid" and t["asteroid"][0] == "(1) Ceres"


def test_minus_mean_keeps_a_moving_saturated_core():
    mover = lambda i: gauss(60 + 1.0 * i, 60, 50.0, 2.5)
    eps = visits([mover], n_visits=3)
    sat = []
    for i in range(3):
        m = np.zeros((N, N), bool)
        m[57:64, 57 + i:64 + i] = True
        sat.append(m)
    t, _ = search.apply_cuts(search.find_residuals(eps, method="minus_mean"), eps, sat)
    end = t[(t["pair"] == "2-mean") & (np.hypot(np.asarray(t["x"]) - 61, np.asarray(t["y"]) - 60) < 5)]
    assert len(end) and set(end["cut"]) == {""} and end["saturated"].all()


def test_minus_mean_movers_use_the_mean_date():
    eps = visits([lambda i: gauss(60 - 1.0 * i, 60, 4.0)], n_visits=3)     # 1 px east per 180 d
    t, _ = search.apply_cuts(search.find_residuals(eps, method="minus_mean"), eps)
    c = search.classify(t, eps)
    m = c[c["type"] == "mover"]
    assert set(m["pair"]) <= {"0-mean", "2-mean"}                          # 1-mean: no baseline
    assert len(m) >= 1 and all(abs(pa - 90) < 15 for pa in m["pm_pa_deg"])   # east, also for visit 0


def test_match_prefers_the_bright_or_comoving_source(monkeypatch):
    eps, c = _classified([lambda i: gauss(60 - 1.5 * i, 60, 4.0), lambda i: gauss(30, 90, 2.0 if i else 0.0)])
    wcs = eps[0]["wcs"]
    m = c[c["type"] == "mover"][0]
    s = c[c["type"] != "mover"][0]
    pm_ = wcs.pixel_to_world(m["x"], m["y"])
    ps = wcs.pixel_to_world(s["x"], s["y"])
    d = 1.0 / 3600
    _fake_catalogues(monkeypatch, [("faint-static", pm_.ra.deg, pm_.dec.deg + 0.3 * d, 21.0, 0.0),
                                   ("bright-mover", pm_.ra.deg, pm_.dec.deg + 1.5 * d, 8.0, float(m["pm_arcsec_yr"]) * 1000),
                                   ("faint", ps.ra.deg, ps.dec.deg + 0.2 * d, 21.0, 0.0),
                                   ("bright", ps.ra.deg, ps.dec.deg + 2.0 * d, 12.0, 0.0)], asteroid_rows=[])
    t, _ = search.crossmatch(c, eps)
    got = dict(zip(t["type"], t["gaia_source_id"]))
    assert got["mover"] == "bright-mover" and got[s["type"]] == "bright"
