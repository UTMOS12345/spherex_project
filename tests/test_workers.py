"""Worker processes (spherex.workers): spawn, order, identical output for any worker count,
fallback to one process, and use from a script without a main guard."""
import multiprocessing
import os
import subprocess
import sys
import textwrap

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from spherex import epochs, framecache, workers
from spherex.clean import BAD_FLAGS

sys.path.insert(0, os.path.dirname(__file__))
import workers_helpers as H  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_pool(monkeypatch):
    workers._shutdown()
    monkeypatch.setattr(workers, "_failed", False)
    monkeypatch.setattr(workers, "_warned", False)
    monkeypatch.setattr(workers, "MIN_TASKS", 2)
    monkeypatch.setattr(workers, "MIN_TASKS_NEW_POOL", 2)
    yield
    workers._shutdown()


def test_spawn_order_and_other_processes():
    out = workers.run(H.square_pid, [(i,) for i in range(12)], workers=3)
    assert [v for v, _ in out] == [i * i for i in range(12)]           # order kept
    pids = {pid for _, pid in out}
    assert os.getpid() not in pids and 1 <= len(pids) <= 3
    assert workers._pool._mp_context.get_start_method() == "spawn"     # also on Linux


def test_serial_with_one_worker_or_few_tasks():
    out = workers.run(H.square_pid, [(i,) for i in range(5)], workers=1)
    assert {pid for _, pid in out} == {os.getpid()} and workers._pool is None
    out = workers.run(H.square_pid, [(3,)], workers=4)                  # below MIN_TASKS
    assert out == [(9, os.getpid())]


def test_a_new_pool_only_for_enough_work(monkeypatch):
    """Starting workers costs ~1.5 s: a few tasks run here unless a pool is already running."""
    monkeypatch.setattr(workers, "MIN_TASKS_NEW_POOL", 10)
    out = workers.run(H.square_pid, [(i,) for i in range(5)], workers=2)
    assert {p for _, p in out} == {os.getpid()} and workers._pool is None
    workers.prestart(2)                                                 # e.g. the app, on a target
    out = workers.run(H.square_pid, [(i,) for i in range(5)], workers=2)
    assert os.getpid() not in {p for _, p in out}


def test_n_workers_setting(monkeypatch):
    monkeypatch.setenv("SPHEREX_WORKERS", "3")
    assert workers.n_workers() == 3
    monkeypatch.setenv("SPHEREX_WORKERS", "0")
    assert workers.n_workers() == 1
    monkeypatch.delenv("SPHEREX_WORKERS")
    assert workers.n_workers() == max(1, min(os.cpu_count() or 1, 8))


def test_pool_cannot_start_falls_back_once(monkeypatch, capsys):
    def no_pool(*a, **k):
        raise OSError("no processes here")
    monkeypatch.setattr(workers, "ProcessPoolExecutor", no_pool)
    done = []
    out = workers.run(H.square_pid, [(i,) for i in range(4)], on_done=done.append, workers=4)
    assert [v for v, _ in out] == [0, 1, 4, 9] and {p for _, p in out} == {os.getpid()}
    assert sorted(done) == [0, 1, 2, 3]
    workers.run(H.square_pid, [(i,) for i in range(4)], workers=4)     # stays serial, no 2nd message
    msg = capsys.readouterr().out
    assert msg.count("worker processes unavailable") == 1 and "no processes here" in msg


def test_worker_killed_mid_run_finishes_serially(capsys):
    """A worker dying (BrokenProcessPool): the remaining tasks run in this process, the
    results are complete and in order, the fallback is logged once."""
    out = workers.run(H.die_on, [(i, 5, os.getpid()) for i in range(8)], workers=2)
    assert out == [i * 10 for i in range(8)]
    assert capsys.readouterr().out.count("worker processes unavailable") == 1
    assert workers._failed and workers._pool is None


def test_task_error_is_raised_as_is_and_pool_stays():
    with pytest.raises(ValueError, match="bad task 3"):
        workers.run(H.fail_on, [(i, 3) for i in range(6)], workers=2)
    assert not workers._failed
    assert workers.run(H.fail_on, [(i, -1) for i in range(6)], workers=2) == list(range(6))


def test_script_without_main_guard(tmp_path):
    """Spawn re-runs the parent's main script in workers unless told not to: a script without
    `if __name__ == "__main__"` must run once and use the pool."""
    script = tmp_path / "noguard.py"
    script.write_text(textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {os.path.dirname(__file__)!r})
        from spherex import workers
        import workers_helpers as H
        workers.MIN_TASKS = workers.MIN_TASKS_NEW_POOL = 2
        print("RAN", flush=True)
        out = workers.run(H.square_pid, [(i,) for i in range(6)], workers=2)
        print("PIDS", len({{p for _, p in out}} - {{os.getpid()}}), flush=True)
    """))
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "SPHEREX_DEMO": "1"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("RAN") == 1 and "unavailable" not in r.stdout
    assert "PIDS 1" in r.stdout or "PIDS 2" in r.stdout


# ---- the real per-frame task: identical layers for any number of workers
def _fake_cutout(path, seed, centre):
    """A small SPHEREx-like file: IMAGE, ZODI, VARIANCE, FLAGS with a rotated TAN WCS."""
    rng = np.random.default_rng(seed)
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [centre.ra.deg + 0.001 * seed, centre.dec.deg - 0.0007 * seed]
    w.wcs.crpix = [30.5, 30.5]
    a = np.deg2rad(10 + 7 * seed)
    w.wcs.cd = 6.2 / 3600 * np.array([[-np.cos(a), np.sin(a)], [np.sin(a), np.cos(a)]])
    img = rng.normal(5, 1, (60, 60)).astype("f4")
    img[30, 30] += 200
    flags = np.zeros((60, 60), "i4")
    flags[5:8, 40:44] = 1 << 0                          # MP_TRANSIENT
    fh = fits.Header({"MSKN0000": "TRANSIENT", "MSKN0001": "OVERFLOW", "MSKN0002": "SUR_ERROR", "MSKN0021": "SOURCE"})
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(img, w.to_header(), name="IMAGE"),
                  fits.ImageHDU(np.full((60, 60), 4.0, "f4"), name="ZODI"),
                  fits.ImageHDU(np.ones((60, 60), "f4"), name="VARIANCE"),
                  fits.ImageHDU(flags, fh, name="FLAGS")]).writeto(path)
    return path


@pytest.mark.parametrize("cache_on", [False, True])
def test_stack_identical_for_any_worker_count(tmp_path, monkeypatch, cache_on):
    monkeypatch.setenv("SPHEREX_FRAME_CACHE", "1" if cache_on else "0")
    centre = SkyCoord(150.0 * u.deg, 2.0 * u.deg)
    paths = [_fake_cutout(tmp_path / f"c{i}.fits", i, centre) for i in range(7)]
    grid, shape = epochs.make_grid(centre, 4.0, 3.0)
    results = {}
    for n in (1, 2, 4):
        monkeypatch.setenv("SPHEREX_WORKERS", str(n))
        monkeypatch.setattr(framecache, "FRAME_DIR", tmp_path / f"fp{n}")
        stack, cov = epochs.stack_epoch(paths, grid, shape)
        results[n] = (stack.tobytes(), cov.tobytes())
        if cache_on:                                   # the workers stored every frame
            assert len(list((tmp_path / f"fp{n}").rglob("*.npy"))) == 7
            again = epochs.stack_epoch(paths, grid, shape)            # now all hits
            assert again[0].tobytes() == stack.tobytes()
    assert results[1] == results[2] == results[4]
    assert np.isfinite(np.frombuffer(results[1][0])).any()


def test_grid_rebuilt_from_params_is_exact():
    centre = SkyCoord(269.4485 * u.deg, 4.7393 * u.deg)
    for size, pix in [(4.0, 3.0), (10.0, 3.0), (2.0, 1.7)]:
        w, shape = epochs.make_grid(centre, size, pix)
        w2, shape2 = epochs.grid_from_params(epochs.grid_params(w, shape))
        assert framecache.grid_key(w2, shape2) == framecache.grid_key(w, shape)
        assert w2.wcs.crval.tobytes() == w.wcs.crval.tobytes()
