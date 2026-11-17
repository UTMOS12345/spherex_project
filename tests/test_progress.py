"""Progress helpers: safe reporting, the running-count adapter and the time estimate."""
import pytest

from spherex import progress as P


@pytest.fixture(autouse=True)
def no_download_status(monkeypatch):
    """The exact-text tests below do not depend on the live download limiter."""
    monkeypatch.setattr(P, "_DOWNLOAD_STATUS", [None])


def test_download_line_shows_concurrency_and_busy(monkeypatch):
    clock = Clock()
    est = P.Estimate(clock)
    monkeypatch.setattr(P, "_DOWNLOAD_STATUS", [lambda: "archive busy, slowing down: 3 at once"])
    est.update(P.DOWNLOADING, 0, 61)
    assert "archive busy, slowing down: 3 at once" not in est.update(P.DOWNLOADING, 0, 61)["text"]  # not yet
    clock.t = 2.0
    assert est.update(P.DOWNLOADING, 1, 61)["text"] == "downloading images · 1 / 61 · archive busy, slowing down: 3 at once"
    assert "at once" not in est.update(P.CLEANING, 1, 61)["text"]          # downloads only



class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_report_ignores_callback_errors():
    def bad(stage, done, total):
        raise RuntimeError("boom")
    P.report(bad, P.DOWNLOADING, 1, 2)          # must not raise
    P.report(None, P.DOWNLOADING, 1, 2)         # no callback: nothing happens


def test_shifted_counts_on_from_offset():
    seen = []
    cb = P.shifted(lambda *a: seen.append(a), P.MEASURING, 10, 30)
    cb(P.DOWNLOADING, 3, 5)                     # other stages are dropped
    cb(P.MEASURING, 0, 5)                       # the restart at 0 is dropped
    cb(P.MEASURING, 2, 5)
    assert seen == [(P.MEASURING, 12, 30)]


def test_no_estimate_before_two_items_then_average_per_item():
    clock = Clock()
    est = P.Estimate(clock)
    assert est.update(P.DOWNLOADING, 0, 61)["seconds_left"] is None
    clock.t = 3.0
    first = est.update(P.DOWNLOADING, 1, 61)
    assert first["seconds_left"] is None and first["text"] == "downloading images · 1 / 61"
    clock.t = 6.0
    info = est.update(P.DOWNLOADING, 2, 61)     # 3 s per item, 59 left
    assert info["seconds_left"] == 177.0
    assert info["count"] == "2 / 61"
    assert info["text"] == "downloading images · 2 / 61 · about 3 min left"


def test_new_stage_restarts_the_clock_and_finished_stage_has_no_estimate():
    clock = Clock()
    est = P.Estimate(clock)
    est.update(P.DOWNLOADING, 0, 4)
    clock.t = 100.0
    assert est.update(P.DOWNLOADING, 4, 4)["text"] == "downloading images · 4 / 4"
    est.update(P.CLEANING, 0, 4)
    clock.t = 101.0
    est.update(P.CLEANING, 1, 4)
    clock.t = 102.0
    assert est.update(P.CLEANING, 2, 4)["seconds_left"] == 2.0      # 1 s per item, not 25


def test_retries_and_busy_replies_counted_per_download_stage():
    clock = Clock()
    est = P.Estimate(clock)
    P.note_failed_try("HTTP 503", retrying=True)                   # before the stage: not counted
    est.update(P.DOWNLOADING, 0, 10)
    P.note_failed_try("HTTP 503", retrying=True)
    P.note_failed_try("TimeoutError: no answer", retrying=True)
    info = est.update(P.DOWNLOADING, 1, 10)
    assert (info["retries"], info["busy"]) == (2, 1)
    assert info["text"].endswith("2 retries (1 busy)")
    assert est.update(P.MEASURING, 0, 3)["retries"] == 0           # only shown for downloads


def test_time_left_text():
    assert P.time_left_text(4) == "a few seconds left"
    assert P.time_left_text(42) == "about 40 s left"
    assert P.time_left_text(150) == "about 2 min left"
    assert P.time_left_text(3 * 3600 + 20 * 60) == "about 3 h 20 min left"
