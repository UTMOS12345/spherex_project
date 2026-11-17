"""Progress reporting for the slow api functions.

A progress callback is any callable progress(stage, done, total):
    stage  short plain text, one of STAGES ("downloading images", ...)
    done   items finished so far in this stage (0 when the stage starts)
    total  items in this stage
It is called at the start of each stage (done=0) and after each item. It is only ever called
from the thread doing the work, and an exception raised inside it is ignored: progress
reporting can never change or break a result.

Estimate turns those calls into a line for a progress bar, with the time left:
    est = Estimate()
    def progress(stage, done, total):
        info = est.update(stage, done, total)
        print(info["text"])          # "downloading images · 23 / 61 · about 2 min left"
"""
import threading
import time

from .text import plural

SEARCHING = "searching the archive"
DOWNLOADING = "downloading images"
CLEANING = "cleaning and aligning"
STACKING = "stacking visits"
MEASURING = "measuring"
DRAWING = "drawing"
STAGES = (SEARCHING, DOWNLOADING, CLEANING, STACKING, MEASURING, DRAWING)


def report(progress, stage, done, total):
    """Call progress(stage, done, total) if a callback was given; ignore anything it raises."""
    if progress is None:
        return
    try:
        progress(stage, int(done), int(total))
    except Exception:
        pass


def shifted(progress, stage, offset, grand_total):
    """A callback that forwards only `stage`, counted from `offset` out of `grand_total`.
    Lets a loop over parts (the visits of spectrum_figure(all_visits=True)) report one running
    count instead of restarting at 0 for every part; other stages are dropped."""
    if progress is None:
        return None

    def forward(s, done, total):
        if s == stage and done > 0:
            report(progress, stage, offset + done, grand_total)
    return forward


# ------------------------------------------------------------------ retries (net.with_retries)
_RETRY_LOCK = threading.Lock()
_RETRIES = {"retries": 0, "busy": 0}


def note_failed_try(err, retrying):
    """Called for every failed server call (net.with_retries, cutout downloads): counts retries,
    and replies that said "overloaded" (HTTP 429, 502, 503, 504). Process-wide counters;
    Estimate shows the change per stage."""
    with _RETRY_LOCK:
        _RETRIES["retries"] += bool(retrying)
        _RETRIES["busy"] += any(f"HTTP {c}" in str(err) for c in (429, 502, 503, 504))


_DOWNLOAD_STATUS = [None]


def set_download_status(fn):
    """fn() -> short text about the downloads right now ("6 at once", "archive busy, slowing
    down: 3 at once"); shown on the "downloading images" line. Set by spherex.download."""
    _DOWNLOAD_STATUS[0] = fn


def download_status():
    fn = _DOWNLOAD_STATUS[0]
    if fn is None:
        return ""
    try:
        return fn() or ""
    except Exception:
        return ""


def retry_counts():
    """(retries, busy replies) so far in this process."""
    with _RETRY_LOCK:
        return _RETRIES["retries"], _RETRIES["busy"]


# ------------------------------------------------------------------ time estimate
MIN_ITEMS_FOR_ESTIMATE = 2


def time_left_text(seconds):
    """Seconds -> 'about 2 min left' (rounded, so the line does not flicker)."""
    if seconds is None:
        return ""
    if seconds < 10:
        return "a few seconds left"
    if seconds < 60:
        return f"about {int(round(seconds / 5.0) * 5)} s left"
    if seconds < 3600:
        return f"about {int(round(seconds / 60.0))} min left"
    h, m = divmod(int(round(seconds / 60.0)), 60)
    return f"about {h} h {m} min left" if m else f"about {h} h left"


class Estimate:
    """Feed it every progress(stage, done, total) call; update() returns a dict:
        stage, done, total, count ("23 / 61"), fraction (0..1),
        seconds_left (None until MIN_ITEMS_FOR_ESTIMATE items of this stage are done),
        time_left ("about 2 min left" or ""), retries, busy (for "downloading images": retries and
        HTTP 503 "busy" replies since the stage began, else 0), and
        text: "downloading images · 23 / 61 · about 2 min left · 3 retries (2 busy)".
    The estimate is the average time per item so far in the current stage times the items left.
    A new stage (or a count going back) starts the clock again. clock: for tests."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._stage = None
        self._t0 = 0.0
        self._base = 0              # done when the clock started (0 for a stage reported from its start)
        self._last = 0
        self._r0 = (0, 0)

    def update(self, stage, done, total):
        now = self._clock()
        done, total = int(done), int(total)
        if stage != self._stage or done < self._last:
            self._stage, self._t0, self._base, self._r0 = stage, now, done, retry_counts()
        self._last = done
        finished = done - self._base
        seconds = None
        if total and done >= total:
            seconds = 0.0
        elif finished >= MIN_ITEMS_FOR_ESTIMATE:
            seconds = (now - self._t0) / finished * (total - done)
        retries = busy = 0
        if stage == DOWNLOADING:
            r, b = retry_counts()
            retries, busy = r - self._r0[0], b - self._r0[1]
        parts = [stage, f"{done} / {total}"]
        if stage == DOWNLOADING and 0 < total and done < total and (finished or retries or busy):
            note = download_status()          # "6 at once" / "archive busy, slowing down: 3 at once"
            if note:
                parts.append(note)
        if seconds is not None and done < total:
            parts.append(time_left_text(seconds))
        if retries or busy:
            parts.append(f"{plural(retries, 'retry', 'retries')}" + (f" ({busy} busy)" if busy else ""))
        return {"stage": stage, "done": done, "total": total, "count": f"{done} / {total}",
                "fraction": min(max(done / total, 0.0), 1.0) if total else 0.0,
                "seconds_left": seconds, "time_left": time_left_text(seconds) if done < total else "",
                "retries": retries, "busy": busy, "text": " · ".join(parts)}
