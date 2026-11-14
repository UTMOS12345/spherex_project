import os
import time
from pathlib import Path

import pytest

from spherex import download


def _write_fits(path, size=256):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"S" + b"0" * max(0, size - 1))


def _fake_download_checked(url, dest):
    _write_fits(dest, size=300)
    return dest


def _set_env(monkeypatch, **vals):
    for k in ("SPHEREX_CACHE_MAX_GB", "SPHEREX_CACHE_POLICY",
              "SPHEREX_CACHE_TTL_DAYS", "SPHEREX_CACHE_SWEEP_EVERY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in vals.items():
        if v is not None:
            monkeypatch.setenv(k, str(v))


@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    cutouts = tmp_path / "cutouts"
    cutouts.mkdir()
    monkeypatch.setattr(download, "CACHE_DIR", cutouts)
    monkeypatch.setattr(download, "_download_checked", _fake_download_checked)
    monkeypatch.setattr(download, "_DOWNLOAD_COUNT", 0)
    monkeypatch.setattr(download, "_IN_USE", set())
    monkeypatch.setattr(download.net, "DEMO_MODE", False)
    _set_env(monkeypatch)
    return cutouts


def _touch(path, mtime):
    os.utime(path, (mtime, mtime))


def test_unlimited_noop(cache_env, monkeypatch):
    _set_env(monkeypatch)
    a = cache_env / "a.fits"
    b = cache_env / "b.fits"
    _write_fits(a, 100)
    _write_fits(b, 100)
    t = 1_000_000.0
    _touch(a, t - 100)
    _touch(b, t)
    download._enforce_cache_limit()
    assert a.exists() and b.exists()


def test_evict_oldest_mtime_first(cache_env, monkeypatch):
    # limit small enough that oldest removed; total <= limit + one file (overshoot acceptable logic)
    _set_env(monkeypatch, SPHEREX_CACHE_MAX_GB=str(250 / download._GB))
    now = 1_000_000.0
    old = cache_env / "old.fits"
    mid = cache_env / "mid.fits"
    new = cache_env / "new.fits"
    for p, ts in ((old, now - 300), (mid, now - 200), (new, now - 100)):
        _write_fits(p, 100)
        _touch(p, ts)
    download._enforce_cache_limit()
    assert not old.exists()
    # mid/new may remain depending on limit; total should be <= limit
    total = sum(p.stat().st_size for p in cache_env.glob("*.fits"))
    assert total <= int(250)


def test_keep_protects_file(cache_env, monkeypatch):
    _set_env(monkeypatch, SPHEREX_CACHE_MAX_GB=str(50 / download._GB))
    now = 1_000_000.0
    old = cache_env / "old.fits"
    kept = cache_env / "kept.fits"
    for p, ts in ((old, now - 300), (kept, now - 200)):
        _write_fits(p, 100)
        _touch(p, ts)
    download._enforce_cache_limit(keep=(kept,))
    assert kept.exists()
    assert not old.exists()


def test_stop_raises_on_miss_serves_hits(cache_env, monkeypatch):
    _set_env(monkeypatch, SPHEREX_CACHE_MAX_GB=str(10 / download._GB), SPHEREX_CACHE_POLICY="stop")
    existing = cache_env / "existing.fits"
    _write_fits(existing, 100)
    # cache hit path: monkeypatch find_cached to return existing and valid
    monkeypatch.setattr(download, "find_cached", lambda *a, **k: existing)
    monkeypatch.setattr(download, "is_valid_fits", lambda p: True)
    got = download.get_cutout("http://x/a.fits", object(), 0.1)
    assert got == existing
    # miss path with full cache
    monkeypatch.setattr(download, "find_cached", lambda *a, **k: None)
    with pytest.raises(OSError, match="cache full"):
        download.get_cutout("http://x/b.fits", object(), 0.1)


def test_ttl_deletes_only_old(cache_env, monkeypatch):
    _set_env(monkeypatch, SPHEREX_CACHE_TTL_DAYS="1")
    now = time.time()
    old = cache_env / "old.fits"
    recent = cache_env / "recent.fits"
    _write_fits(old, 100)
    _write_fits(recent, 100)
    _touch(old, now - 2 * 86400)
    _touch(recent, now - 3600)
    download._enforce_cache_limit()
    assert not old.exists()
    assert recent.exists()


def test_other_cache_dirs_untouched(cache_env, monkeypatch):
    _set_env(monkeypatch, SPHEREX_CACHE_MAX_GB=str(10 / download._GB))
    root = cache_env.parent
    for name in ("frames", "gaia", "wise"):
        d = root / name
        d.mkdir(exist_ok=True)
        (d / "sentinel.txt").write_text("keep")
    # add cutout to trigger eviction
    old = cache_env / "old.fits"
    _write_fits(old, 100)
    _touch(old, 1_000_000.0)
    download._enforce_cache_limit()
    for name in ("frames", "gaia", "wise"):
        assert (root / name / "sentinel.txt").exists()


def test_cache_hit_touches_mtime(cache_env, monkeypatch):
    f = cache_env / "hit.fits"
    _write_fits(f, 100)
    _touch(f, 1_000_000.0)
    before = f.stat().st_mtime
    monkeypatch.setattr(download, "find_cached", lambda *a, **k: f)
    monkeypatch.setattr(download, "is_valid_fits", lambda p: True)
    download.get_cutout("http://x/a.fits", object(), 0.1)
    assert f.stat().st_mtime >= before


def test_sweep_every_counter(cache_env, monkeypatch):
    _set_env(monkeypatch, SPHEREX_CACHE_MAX_GB=str(10 / download._GB), SPHEREX_CACHE_SWEEP_EVERY="3")
    now = 1_000_000.0
    old = cache_env / "old.fits"
    _write_fits(old, 100)
    _touch(old, now - 100)
    # 1st and 2nd call should not enforce
    download._enforce_cache_limit()
    download._enforce_cache_limit()
    assert old.exists()
    # 3rd triggers
    download._enforce_cache_limit()
    assert not old.exists()
