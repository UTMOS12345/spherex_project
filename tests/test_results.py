"""Saved results (spherex.results): keys, atomic writes, broken files, and 'complete only'."""
import pickle

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time

from spherex import api, download, results
from spherex.epochs import epoch_grid


@pytest.fixture
def res_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(results, "RESULTS_DIR", tmp_path / "results")
    results._mem.clear()
    yield tmp_path / "results"
    results._mem.clear()


STAR = SkyCoord(133.79 * u.deg, -7.24 * u.deg)
MOVER = SkyCoord(269.45 * u.deg, 4.69 * u.deg, obstime=Time(2000.0, format="jyear"),
                 pm_ra_cosdec=-800 * u.mas / u.yr, pm_dec=10000 * u.mas / u.yr)


def test_key_changes_with_every_setting(res_dir):
    base = dict(detector="D2", fov=4.0, wl=None, days=60, clip=True, frames="abc")
    p = results.result_path("WISE 0855", "stacks", STAR, **base)
    assert p.parent == res_dir / "WISE_0855" and p.name.startswith("stacks_")
    assert results.result_path("WISE 0855", "stacks", STAR, **base) == p         # stable
    for change in (dict(detector="D6"), dict(fov=6.0), dict(wl=(4.4, 4.7)), dict(days=7),
                   dict(clip=False), dict(frames="abd")):
        assert results.result_path("WISE 0855", "stacks", STAR, **{**base, **change}) != p, change
    assert results.result_path("x", "stacks", MOVER, **base) != results.result_path("x", "stacks", STAR, **base)
    assert results.result_path("WISE 0855", "light_curve", STAR, **base) != p


def test_version_is_part_of_the_key(res_dir, monkeypatch):
    p = results.result_path("t", "spectrum", STAR, frames="f")
    monkeypatch.setattr(results, "RESULTS_VERSION", results.RESULTS_VERSION + 1)
    assert results.result_path("t", "spectrum", STAR, frames="f") != p


def test_frames_key_follows_the_frame_list():
    a = Table({"access_url": ["u1", "u2"]})
    b = Table({"access_url": ["u1", "u2", "u3"]})            # a newer frame, or another release
    assert results.frames_key(a) == results.frames_key(Table({"access_url": ["u1", "u2"]}))
    assert results.frames_key(a) != results.frames_key(b)


def test_save_load_roundtrip_is_exact_and_atomic(res_dir):
    p = results.result_path("t", "light_curve", STAR, frames="f")
    obj = Table({"mjd": [60000.123456789], "flux_mjy": [0.1 + 0.2]})
    results.save(p, obj)
    assert not list(p.parent.glob(".*.part"))                 # no temporary file left
    results._mem.clear()                                      # force a read from disk
    back = results.load(p)
    assert back["mjd"][0] == obj["mjd"][0] and back["flux_mjy"][0] == obj["flux_mjy"][0]


def test_broken_or_missing_file_means_recompute(res_dir):
    p = results.result_path("t", "spectrum", STAR, frames="f")
    assert results.load(p) is None
    p.parent.mkdir(parents=True)
    p.write_bytes(b"not a pickle")
    assert results.load(p) is None


def test_preload_reads_into_memory_only(res_dir):
    p = results.result_path("t", "stacks", STAR, frames="f")
    results.save(p, [1, 2, 3])
    results._mem.clear()
    assert results.preload([p, p.with_name("missing.pkl")]) == 1
    p.unlink()                                                # now only memory has it
    assert results.load(p) == [1, 2, 3]


def test_incomplete_results_are_not_saved(res_dir):
    p = results.result_path("t", "stacks", STAR, frames="f")

    def compute_with(n_missing):
        def compute():
            download.note_missing(n_missing)
            return "result"
        return compute
    assert api._compute_and_save(p, compute_with(2)) == "result"
    assert not p.exists()                                     # 2 images were missing: not saved
    api._compute_and_save(p, compute_with(0))
    assert p.exists()


def test_rebuilt_grid_is_the_same_wcs():
    frames = Table({"mjd": [60000.0, 60100.0, 60400.0]})
    w1, s1 = epoch_grid(frames, MOVER, 4.0, 3.0)
    w2, s2 = epoch_grid(frames, MOVER, 4.0, 3.0)
    assert s1 == s2
    for attr in ("crval", "crpix", "cdelt", "pc"):
        assert np.array_equal(getattr(w1.wcs, attr), getattr(w2.wcs, attr))
    pix = np.array([[10.5, 20.25], [0.0, 79.0]])
    assert np.array_equal(w1.wcs_pix2world(pix, 0), w2.wcs_pix2world(pix, 0))
    # what pickling a WCS does (via a FITS header) is NOT exact enough, hence the rebuild
    w3 = pickle.loads(pickle.dumps(w1))
    assert np.allclose(w1.wcs_pix2world(pix, 0), w3.wcs_pix2world(pix, 0), rtol=0, atol=1e-9)
