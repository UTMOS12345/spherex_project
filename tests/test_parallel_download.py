"""Parallel cutout downloads: same results, order and file names for 1 and 6 workers;
progress only on the calling thread; no temporary files left behind. Offline: the download
itself is replaced by a fake that writes a small FITS file after a random delay."""
import random
import threading
import time

import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.io import fits

from spherex import download, net


@pytest.fixture
def fake_irsa(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(net, "DEMO_MODE", False)
    calls = []
    lock = threading.Lock()

    def fake_download_file(url, cache=False, timeout=None, show_progress=False):
        time.sleep(random.uniform(0.0, 0.03))           # finish out of order
        with lock:
            calls.append(url)
        path = tmp_path / f"irsa_{len(calls)}_{threading.get_ident()}.tmp"
        frame = int(url.split("frame")[1].split(".fits")[0])
        hdus = fits.HDUList([fits.PrimaryHDU(),
                             fits.ImageHDU(np.full((4, 4), frame, "f4"), name="IMAGE"),
                             fits.ImageHDU(np.zeros((2, 4, 4), "f4"), name="PSF")])
        hdus.writeto(path)
        return str(path)
    monkeypatch.setattr(download, "download_file", fake_download_file)
    return tmp_path, calls


def _requests(n):
    c = SkyCoord(133.79, -7.24, unit="deg")
    reqs = [(f"https://irsa.example/frame{i}.fits", c, 0.1) for i in range(n)]
    return reqs + [reqs[3], reqs[0]]                   # repeated requests


@pytest.mark.parametrize("workers", [1, 6])
def test_order_names_and_progress(fake_irsa, workers):
    folder, calls = fake_irsa
    seen, main = [], threading.get_ident()
    out = download.get_cutouts(_requests(12), lambda *a: seen.append((threading.get_ident(), a)),
                               workers=workers)
    assert len(out) == 14 and not any(isinstance(p, OSError) for p in out)
    for i, p in enumerate(out[:12]):
        assert p.name == f"frame{i}__133.79000_-7.24000_0.25.fits"
        with fits.open(p) as h:
            assert h["IMAGE"].data[0, 0] == i and "PSF" not in h
    assert out[12] == out[3] and out[13] == out[0]
    assert len(calls) == 12                            # each frame downloaded once
    assert {t for t, _ in seen} == {main}              # callbacks only on the calling thread
    assert [a[1] for _, a in seen] == list(range(15))  # 0, then one per request, in order
    assert not list(folder.glob(".*.part")) and not list(folder.glob("*.tmp"))


def test_cached_files_are_not_downloaded_again(fake_irsa):
    folder, calls = fake_irsa
    first = download.get_cutouts(_requests(5), workers=6)
    again = download.get_cutouts(_requests(5), workers=6)
    assert first == again and len(calls) == 5


def test_failures_come_back_in_place(fake_irsa, monkeypatch):
    def broken(url, dest):
        if "frame2." in url:
            raise OSError("boom")
        return dest.write_bytes(b"") or dest
    monkeypatch.setattr(download, "_download_adaptive", lambda url, dest, tries, limit: broken(url, dest))
    out = download.get_cutouts(_requests(4)[:4], workers=6)
    assert isinstance(out[2], OSError)
    assert [isinstance(p, OSError) for p in out] == [False, False, True, False]


def test_worker_setting(monkeypatch):
    monkeypatch.setenv("SPHEREX_DOWNLOAD_WORKERS", "3")
    assert download.download_workers() == 3
    monkeypatch.setenv("SPHEREX_DOWNLOAD_WORKERS", "0")
    assert download.download_workers() == 1
    monkeypatch.setenv("SPHEREX_DOWNLOAD_WORKERS", "x")
    assert download.download_workers() == 6
    monkeypatch.delenv("SPHEREX_DOWNLOAD_WORKERS")
    assert download.download_workers() == 6


def test_counting_stops_before_any_download(fake_irsa):
    folder, calls = fake_irsa
    download.get_cutouts(_requests(4)[:3], workers=6)           # frames 0-2 cached
    with download.counting(), pytest.raises(download.DownloadCount) as c:
        download.get_cutouts(_requests(8), workers=6)           # 5 new frames, 2 repeats
    assert (c.value.missing, c.value.total) == (5, 10)
    assert len(calls) == 3                                      # nothing downloaded while counting
    assert len(download.get_cutouts(_requests(8), workers=6)) == 10   # normal again afterwards
    assert len(calls) == 8


@pytest.mark.parametrize("demo", [False, True])
def test_trusted_cached_files_are_not_opened(fake_irsa, monkeypatch, demo):
    """get_cutouts(trusted=...): a cached file the caller vouches for is used without
    is_valid_fits (but its mtime is renewed); every other cached file is still checked."""
    folder, calls = fake_irsa
    reqs = _requests(6)[:6]
    first = download.get_cutouts(reqs, workers=1)                  # download all six
    monkeypatch.setattr(net, "DEMO_MODE", demo)
    checked = []
    real_check = download.is_valid_fits
    monkeypatch.setattr(download, "is_valid_fits", lambda p: checked.append(p) or real_check(p))
    for p in first:
        import os
        os.utime(p, (1, 1))
    trusted_set = set(first[:4])
    out = download.get_cutouts(reqs, workers=1, trusted=lambda p: p in trusted_set)
    assert out == first                                            # same paths, same order
    assert sorted(checked) == sorted(first[4:])                    # only the untrusted were opened
    assert all(p.stat().st_mtime > 1 for p in first)               # all touched (cutout LRU)
    checked.clear()
    download.get_cutouts(reqs, workers=1)                          # no trusted: all checked as before
    assert sorted(checked) == sorted(first)
