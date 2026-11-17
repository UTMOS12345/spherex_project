"""How many cutouts to download at once, adapted to how the archive is coping.

IRSA answered 502/503 for hours on 16-17 Nov 2026, so a fixed number of parallel downloads is
either too timid when the archive is fine or makes things worse when it is struggling.
AdaptiveLimit is additive-increase / multiplicative-decrease (as TCP does):

- it starts at `start` downloads at once (SPHEREX_DOWNLOAD_WORKERS, default 6);
- after a full round of successes (as many as the current limit) it allows one more, up to
  `maximum` (SPHEREX_DOWNLOAD_WORKERS_MAX, default 12);
- a "busy" answer (HTTP 429, 502, 503, 504, a timeout or a dropped connection) halves it,
  down to 1; answers to requests that were already on their way when it was halved do not
  halve it again (one cut per COOLDOWN_S);
- a Retry-After header pauses every new request until that time (at most MAX_PAUSE_S).

A request that waits to be retried does not hold a slot. status_text() is what the progress
line shows: "6 at once", "archive busy, slowing down: 3 at once", "archive busy, waiting 20 s".
"""
import threading
import time

COOLDOWN_S = 2.0          # busy answers within this time of a cut count as the same event
MAX_PAUSE_S = 300.0       # longest Retry-After honoured
SHOW_BUSY_S = 30.0        # the progress line says "slowing down" this long after a cut


class AdaptiveLimit:
    def __init__(self, start, maximum, clock=time.monotonic):
        self.maximum = max(1, int(maximum))
        self.limit = max(1, min(int(start), self.maximum))
        self.active = 0
        self.streak = 0               # successes since the last change
        self.backoffs = 0             # cuts so far
        self.peak = self.limit
        self._last_cut = -1e9
        self._pause_until = 0.0
        self._clock = clock
        self._cond = threading.Condition()

    # -- slots
    def acquire(self):
        with self._cond:
            while True:
                wait = self._pause_until - self._clock()
                if wait <= 0 and self.active < self.limit:
                    self.active += 1
                    return
                self._cond.wait(timeout=min(max(wait, 0.05), 1.0) if wait > 0 else 1.0)

    def release(self):
        with self._cond:
            self.active -= 1
            self._cond.notify_all()

    def slot(self):
        limit = self

        class _Slot:
            def __enter__(self):
                limit.acquire()

            def __exit__(self, *exc):
                limit.release()
                return False
        return _Slot()

    # -- outcomes
    def success(self):
        with self._cond:
            self.streak += 1
            if self.streak >= self.limit and self.limit < self.maximum:
                self.limit += 1
                self.peak = max(self.peak, self.limit)
                self.streak = 0
                self._cond.notify_all()

    def busy(self, retry_after=None):
        """The archive said it is overloaded. -> True when this halved the limit."""
        with self._cond:
            now = self._clock()
            cut = now - self._last_cut >= COOLDOWN_S
            if cut:
                self.limit = max(1, self.limit // 2)
                self.backoffs += 1
                self._last_cut = now
            self.streak = 0
            if retry_after:
                self._pause_until = max(self._pause_until, now + min(float(retry_after), MAX_PAUSE_S))
            return cut

    # -- for the progress line
    def status(self):
        with self._cond:
            now = self._clock()
            return {"limit": self.limit, "maximum": self.maximum, "active": self.active,
                    "backoffs": self.backoffs, "peak": self.peak,
                    "pause_left": max(0.0, self._pause_until - now),
                    "slowing": now - self._last_cut < SHOW_BUSY_S}

    def status_text(self):
        s = self.status()
        if s["pause_left"] >= 1:
            return f"archive busy, waiting {int(round(s['pause_left']))} s"
        if s["slowing"]:
            return f"archive busy, slowing down: {s['limit']} at once"
        return f"{s['limit']} at once"


def parse_retry_after(value, now=None):
    """Retry-After header (seconds, or an HTTP date) -> seconds to wait, or None."""
    if not value:
        return None
    value = str(value).strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        when = parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return max(0.0, when - (time.time() if now is None else now))
