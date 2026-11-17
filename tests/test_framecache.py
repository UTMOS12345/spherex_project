"""Frame cache (spherex.framecache): keys, exact round trip, atomic writes."""
import os
import threading

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import SkyCoord

from spherex import framecache
from spherex.epochs import make_grid
from spherex.clean import BAD_FLAGS

CENTRE = SkyCoord(269.45 * u.deg, 4.69 * u.deg)


@pytest.fixture
def fc(tmp_path, monkeypatch):
    monkeypatch.setattr(framecache, "FRAME_DIR", tmp_path / "frames_proc")
    framecache._digests.clear()
    src = tmp_path / "cutout.fits"
    src.write_bytes(b"SIMPLE  = T" + bytes(range(256)) * 40)
    return src


def _key(src, **change):
    w, shape = make_grid(CENTRE, 4.0, 3.0)
    args = dict(source=src, grid_wcs=w, shape=shape, bad_flags=BAD_FLAGS, keep_saturated_stars=True,
                bloom_radius=4, wl_range=None)
    args.update(change)
    return framecache.frame_key(**args)


def test_key_is_stable(fc):
    assert _key(fc) == _key(fc)


def test_key_same_before_and_after_the_grid_is_used(fc):
    """WCSLIB fills in defaults on first use (cunit '' -> 'deg'): the key must not change."""
    w, shape = make_grid(CENTRE, 4.0, 3.0)
    before = _key(fc, grid_wcs=w, shape=shape)
    w.pixel_to_world(1, 1)
    assert _key(fc, grid_wcs=w, shape=shape) == before == _key(fc)


def test_key_changes_with_every_setting(fc, tmp_path):
    base = _key(fc)
    w, shape = make_grid(CENTRE, 4.0, 3.0)
    other = tmp_path / "other.fits"
    other.write_bytes(fc.read_bytes()[:-1] + b"X")            # same size, one byte different
    shifted = make_grid(CENTRE, 4.0, 3.0)[0]
    shifted.wcs.crval = [shifted.wcs.crval[0] + 1e-12, shifted.wcs.crval[1]]   # far below a marker pixel
    changes = [dict(source=other),
               dict(bad_flags=BAD_FLAGS[:-1]),
               dict(keep_saturated_stars=False),
               dict(bloom_radius=3),
               dict(wl_range=(4.4, 4.7)),
               dict(wl_range=(4.4, 4.8)),
               dict(grid_wcs=make_grid(CENTRE, 5.0, 3.0)[0], shape=make_grid(CENTRE, 5.0, 3.0)[1]),
               dict(grid_wcs=make_grid(CENTRE, 4.0, 2.0)[0], shape=make_grid(CENTRE, 4.0, 2.0)[1]),
               dict(grid_wcs=shifted),
               dict(shape=(shape[0] + 1, shape[1]))]
    keys = [_key(fc, **c) for c in changes]
    assert base not in keys
    assert len(set(keys)) == len(keys), "two different settings share a key"


def test_key_ignores_flag_order_and_mtime(fc):
    k = _key(fc)
    assert _key(fc, bad_flags=list(reversed(BAD_FLAGS))) == k   # the mask is an OR of the flags
    os.utime(fc, (1, 1))                                         # get_cutout touches files on every use
    assert _key(fc) == k


def test_key_changes_with_version(fc, monkeypatch):
    k = _key(fc)
    monkeypatch.setattr(framecache, "FRAME_CACHE_VERSION", framecache.FRAME_CACHE_VERSION + 1)
    assert _key(fc) != k


def test_round_trip_is_exact(fc):
    rng = np.random.default_rng(1)
    a = rng.normal(size=(80, 80))
    a[3:9, 5] = np.nan
    framecache.save("ab" * 32, a)
    back = framecache.load("ab" * 32, (80, 80))
    assert back.dtype == np.float64 and back.tobytes() == a.tobytes()
    framecache.save("cd" * 32, None)                             # frame never sees the range
    assert framecache.load("cd" * 32, (80, 80)) == "none"
    assert framecache.load("ef" * 32, (80, 80)) is None          # never stored
    assert framecache.load("ab" * 32, (81, 80)) is None          # wrong shape: a miss


def test_damaged_entry_is_a_miss(fc):
    p = framecache.entry_path("ab" * 32)
    p.parent.mkdir(parents=True)
    p.write_bytes(b"\x93NUMPY half a file")
    assert framecache.load("ab" * 32, (80, 80)) is None


def test_failed_compute_stores_nothing(fc):
    w, shape = make_grid(CENTRE, 4.0, 3.0)

    def boom():
        raise ValueError("reproject failed")
    with pytest.raises(ValueError):
        framecache.cached_layer(fc, w, shape, boom, BAD_FLAGS, True, 4, None)
    assert not list(framecache.FRAME_DIR.rglob("*.npy"))


def test_hit_skips_compute(fc):
    w, shape = make_grid(CENTRE, 4.0, 3.0)
    calls = []
    layer = np.arange(shape[0] * shape[1], dtype=float).reshape(shape)

    def compute():
        calls.append(1)
        return layer
    a = framecache.cached_layer(fc, w, shape, compute, BAD_FLAGS, True, 4, None)
    b = framecache.cached_layer(fc, w, shape, compute, BAD_FLAGS, True, 4, None)
    assert len(calls) == 1 and a.tobytes() == b.tobytes()


def test_write_is_atomic(fc, monkeypatch):
    """A crash in the middle of writing leaves no entry and no temporary file."""
    def broken_save(f, arr, allow_pickle=False):
        f.write(b"\x93NUMPY partial")
        raise OSError("disk full")
    monkeypatch.setattr(framecache.np, "save", broken_save)
    framecache.save("ab" * 32, np.zeros((4, 4)))
    assert not framecache.entry_path("ab" * 32).exists()
    assert not [p for p in framecache.FRAME_DIR.rglob("*") if p.is_file()]


def test_concurrent_writers_same_key(fc):
    """Many threads storing the same frame at once: one whole, readable file, no leftovers."""
    a = np.random.default_rng(2).normal(size=(200, 200))
    start = threading.Barrier(8)

    def worker():
        start.wait()
        for _ in range(20):
            framecache.save("ab" * 32, a)
            got = framecache.load("ab" * 32, a.shape)
            assert got is None or got.tobytes() == a.tobytes()
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert framecache.load("ab" * 32, a.shape).tobytes() == a.tobytes()
    assert [p.name for p in framecache.FRAME_DIR.rglob("*") if p.is_file()] == [framecache.entry_path("ab" * 32).name]


@pytest.mark.parametrize("off", ["0", "false", "off"])
def test_env_switch_turns_it_off(fc, monkeypatch, off):
    """SPHEREX_FRAME_CACHE=0: always compute, never read or write."""
    monkeypatch.setenv("SPHEREX_FRAME_CACHE", off)
    w, shape = make_grid(CENTRE, 4.0, 3.0)
    calls = []

    def compute():
        calls.append(1)
        return np.zeros(shape)
    framecache.cached_layer(fc, w, shape, compute, BAD_FLAGS, True, 4, None)
    framecache.cached_layer(fc, w, shape, compute, BAD_FLAGS, True, 4, None)
    assert len(calls) == 2
    assert not list(framecache.FRAME_DIR.rglob("*.npy"))


def test_stacker_goes_through_the_cache(fc, monkeypatch):
    """epochs._aligned_layer: computed once, then served from the cache, same bytes."""
    from spherex import epochs
    w, shape = make_grid(CENTRE, 4.0, 3.0)
    calls = []
    layer = np.random.default_rng(3).normal(size=shape)
    monkeypatch.setattr(epochs, "_compute_layer", lambda *a: calls.append(a) or layer.copy())
    a = epochs._aligned_layer(fc, w, shape, BAD_FLAGS, True, None)
    b = epochs._aligned_layer(fc, w, shape, BAD_FLAGS, True, None)
    c = epochs._aligned_layer(fc, w, shape, BAD_FLAGS, False, None)    # other setting: computed
    assert len(calls) == 2 and a.tobytes() == b.tobytes() == layer.tobytes() and c is not None


def _fill(n, shape=(64, 64)):
    """n entries of 32 KB + header, mtimes 1000, 1001, ... (key i is the i-th oldest)."""
    keys = [f"{i:02x}" * 32 for i in range(n)]
    for i, k in enumerate(keys):
        framecache.save(k, np.full(shape, float(i)))
        os.utime(framecache.entry_path(k), (1000 + i, 1000 + i))
    return keys


def test_eviction_removes_least_recently_used(fc, monkeypatch):
    monkeypatch.delenv("SPHEREX_CACHE_TTL_DAYS", raising=False)
    monkeypatch.setenv("SPHEREX_FRAME_CACHE_MAX_GB", "0")         # unlimited while filling
    keys = _fill(10)
    one = framecache.entry_path(keys[0]).stat().st_size
    assert framecache.info()["entries"] == 10
    framecache.load(keys[0], (64, 64))                            # a hit: now the most recent
    monkeypatch.setenv("SPHEREX_FRAME_CACHE_MAX_GB", str(6.5 * one / 1024 ** 3))
    n, freed = framecache.sweep(force=True)
    assert (n, freed) == (4, 4 * one)
    left = [k for k in keys if framecache.entry_path(k).exists()]
    assert left == [keys[0]] + keys[5:]                          # 1-4 were the oldest unused
    assert framecache.info()["size_bytes"] <= 6.5 * one
    for i, k in enumerate(keys):                                  # nothing broken: hits or clean misses
        got = framecache.load(k, (64, 64))
        assert (got is None) == (k not in left)
        if got is not None:
            assert (got == float(i)).all()


def test_sweep_runs_after_writes_only_and_respects_unlimited(fc, monkeypatch):
    monkeypatch.delenv("SPHEREX_CACHE_TTL_DAYS", raising=False)
    monkeypatch.setenv("SPHEREX_FRAME_CACHE_MAX_GB", "0")
    keys = _fill(5)
    assert framecache.sweep(force=True) == (0, 0)                # 0 = unlimited
    monkeypatch.setenv("SPHEREX_FRAME_CACHE_MAX_GB", "1e-9")
    framecache._writes = 0
    assert framecache.sweep() == (0, 0)                          # nothing written since: no scan
    assert all(framecache.entry_path(k).exists() for k in keys)
    framecache.save("ff" * 32, np.zeros((64, 64)))               # a write, then the next sweep evicts
    assert framecache.sweep()[0] >= 5


def test_ttl_expires_old_entries(fc, monkeypatch):
    monkeypatch.setenv("SPHEREX_FRAME_CACHE_MAX_GB", "0")
    monkeypatch.setenv("SPHEREX_CACHE_TTL_DAYS", "1")
    keys = _fill(3)                                               # mtimes in 1970: expired
    framecache.save("ff" * 32, np.zeros((64, 64)))               # fresh
    framecache.sweep(force=True)
    assert not any(framecache.entry_path(k).exists() for k in keys)
    assert framecache.entry_path("ff" * 32).exists()


def test_default_cap_and_clear(fc, monkeypatch, tmp_path):
    monkeypatch.delenv("SPHEREX_FRAME_CACHE_MAX_GB", raising=False)
    assert framecache.max_bytes() == int(framecache.DEFAULT_MAX_GB * 1024 ** 3)
    _fill(3)
    cutout = tmp_path / "cutouts" / "keep.fits"                  # a sibling folder: never touched
    cutout.parent.mkdir()
    cutout.write_bytes(b"x")
    n, size = framecache.clear()
    assert n == 3 and size > 0
    assert framecache.info()["entries"] == 0 and cutout.exists()


def test_cli_cache_info_and_clear(fc, monkeypatch, capsys):
    from paramost import cli
    monkeypatch.setattr(cli, "_use_cache_dir", lambda path: None)
    _fill(2)
    import spherex.net
    monkeypatch.setattr(spherex.net, "CACHE_ROOT", framecache.FRAME_DIR.parent)
    assert cli.main(["cache-info"]) == 0
    out = capsys.readouterr().out
    assert "frames_proc/" in out and "2 aligned frames" in out
    assert cli.main(["cache-clear", "frames"]) == 0
    assert "2 aligned frames" in capsys.readouterr().out
    assert framecache.info()["entries"] == 0
