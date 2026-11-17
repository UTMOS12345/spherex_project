"""Adaptive download concurrency (spherex.throttle) and a simulated busy archive: a local HTTP
server answering 503 with Retry-After and 502, served through the real download path."""
import io
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.io import fits

from spherex import download, net, throttle
from spherex import progress as P


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_additive_increase_up_to_the_maximum():
    lim = throttle.AdaptiveLimit(6, 8)
    for _ in range(6):
        lim.success()
    assert lim.limit == 7                      # one more after a full round (6) of successes
    for _ in range(7):
        lim.success()
    assert lim.limit == 8
    for _ in range(50):
        lim.success()
    assert lim.limit == 8 and lim.peak == 8    # never above the maximum


def test_busy_halves_once_per_burst_floor_one():
    clock = Clock()
    lim = throttle.AdaptiveLimit(12, 12, clock=clock)
    assert lim.busy() is True and lim.limit == 6
    assert lim.busy() is False and lim.limit == 6       # same burst: requests already on their way
    clock.t = 3.0
    lim.busy(); clock.t = 6.0; lim.busy(); clock.t = 9.0; lim.busy(); clock.t = 12.0; lim.busy()
    assert lim.limit == 1 and lim.backoffs == 5        # 6 -> 3 -> 1 -> 1 -> 1
    assert lim.status_text() == "archive busy, slowing down: 1 at once"
    clock.t = 100.0
    assert lim.status_text() == "1 at once"


def test_retry_after_pauses_new_requests():
    lim = throttle.AdaptiveLimit(4, 4)
    lim.busy(retry_after=1.2)
    assert lim.status_text().startswith("archive busy, waiting")
    t0 = time.monotonic()
    with lim.slot():
        pass
    assert time.monotonic() - t0 >= 1.0


def test_parse_retry_after():
    assert throttle.parse_retry_after("7") == 7.0
    assert throttle.parse_retry_after(None) is None and throttle.parse_retry_after("soon") is None
    assert 9 <= throttle.parse_retry_after("Tue, 17 Nov 2026 09:00:10 GMT", now=1794906000.0) <= 11


def _fits_bytes(value):
    buf = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.full((4, 4), value, "f4"), name="IMAGE"),
                  fits.ImageHDU(np.zeros((2, 4, 4), "f4"), name="PSF")]).writeto(buf)
    return buf.getvalue()


class BusyArchive:
    """Local server: the first `n503` requests get 503 + Retry-After, the next `n502` get 502,
    then everything is served (each request takes `delay` s). Records the most requests that
    were in progress at once, overall and after the outage."""

    def __init__(self, n503=0, n502=0, retry_after="1", delay=0.05):
        self.lock = threading.Lock()
        self.n503, self.n502, self.retry_after, self.delay = n503, n502, retry_after, delay
        self.seen = self.active = self.max_active = 0
        self.codes = []
        archive = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                with archive.lock:
                    archive.seen += 1
                    k = archive.seen
                    archive.active += 1
                    archive.max_active = max(archive.max_active, archive.active)
                try:
                    time.sleep(archive.delay)
                    if k <= archive.n503:
                        code, body, extra = 503, b"busy", {"Retry-After": archive.retry_after}
                    elif k <= archive.n503 + archive.n502:
                        code, body, extra = 502, b"bad gateway", {}
                    else:
                        frame = int(self.path.split("frame")[1].split(".fits")[0])
                        code, body, extra = 200, _fits_bytes(frame), {}
                    with archive.lock:
                        archive.codes.append(code)
                    self.send_response(code)
                    for k_, v in extra.items():
                        self.send_header(k_, v)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                finally:
                    with archive.lock:
                        archive.active -= 1

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def archive_env(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(net, "DEMO_MODE", False)
    monkeypatch.setattr(download, "RETRY_BASE_S", 0.05)
    monkeypatch.setattr(download, "_LIMIT", None)
    monkeypatch.setenv("SPHEREX_DOWNLOAD_WORKERS", "6")
    monkeypatch.setenv("SPHEREX_DOWNLOAD_WORKERS_MAX", "12")
    monkeypatch.setattr(download, "TICK_S", 0.1)
    return tmp_path


def _reqs(base, n):
    c = SkyCoord(133.79, -7.24, unit="deg")
    return [(f"{base}/frame{i}.fits", c, 0.1) for i in range(n)]


def test_busy_archive_backs_off_honours_retry_after_and_recovers(archive_env):
    archive = BusyArchive(n503=6, n502=6, retry_after="1")
    lines = []
    est = P.Estimate()
    try:
        t0 = time.monotonic()
        out = download.get_cutouts(_reqs(archive.url, 60),
                                   lambda *a: lines.append(est.update(*a)["text"]))
        elapsed = time.monotonic() - t0
    finally:
        archive.close()
    assert not any(isinstance(p, OSError) for p in out), [p for p in out if isinstance(p, OSError)][:2]
    for i, p in enumerate(out):                                   # right file in the right place
        with fits.open(p) as h:
            assert h["IMAGE"].data[0, 0] == i and "PSF" not in h
    lim = download.limiter()
    assert lim.backoffs >= 1                                      # it slowed down...
    assert elapsed >= 1.0                                         # ...waited for Retry-After...
    assert lim.peak > 6 or lim.limit > 1                          # ...and climbed back up
    assert archive.max_active <= 12
    assert any("archive busy" in t for t in lines)                # the user saw it
    assert any("at once" in t for t in lines)


def test_ok_archive_rises_towards_the_maximum(archive_env):
    archive = BusyArchive(delay=0.02)
    try:
        out = download.get_cutouts(_reqs(archive.url, 120))
    finally:
        archive.close()
    assert not any(isinstance(p, OSError) for p in out)
    lim = download.limiter()
    assert lim.backoffs == 0 and lim.limit > 6 and lim.peak <= 12
    assert 6 < archive.max_active <= 12


def test_not_found_is_not_retried(archive_env, monkeypatch):
    calls = []

    def fake_get(url, dest):
        calls.append(url)
        raise download.HTTPStatus(404)
    monkeypatch.setattr(download, "_download_checked", fake_get)
    out = download.get_cutouts(_reqs("http://x", 2), workers=1)
    assert all(isinstance(p, OSError) for p in out) and len(calls) == 2


def test_one_worker_setting_means_one_at_a_time(archive_env, monkeypatch):
    monkeypatch.setenv("SPHEREX_DOWNLOAD_WORKERS", "1")
    monkeypatch.setattr(download, "_LIMIT", None)
    archive = BusyArchive(delay=0.02)
    try:
        out = download.get_cutouts(_reqs(archive.url, 8))
    finally:
        archive.close()
    assert not any(isinstance(p, OSError) for p in out) and archive.max_active == 1
