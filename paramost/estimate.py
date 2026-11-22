"""How long downloading n images takes, roughly: shared by the app and `paramost render`."""
from spherex.download import download_workers

# Measured 16 Nov 2026, 62 new cutouts from IRSA: 1 worker 799 s (12.9 s per image), 6 workers
# 110 s (7.3x faster). IRSA's speed varies, so the estimate uses 13 s and a 6x speed-up.
SECONDS_PER_IMAGE = 13.0
PARALLEL_SPEEDUP = {1: 1.0, 6: 6.0}         # workers -> speed-up; other counts: 0.75 x workers


def download_time(n):
    """Rough time for n new images at the current number of download workers -> 'about 1-2 min'."""
    workers = min(download_workers(), max(n, 1))
    speedup = PARALLEL_SPEEDUP.get(workers, max(1.0, 0.75 * workers))
    seconds = n * SECONDS_PER_IMAGE / speedup
    lo, hi = seconds * 0.7, seconds * 1.5
    if hi < 60:
        return "under a minute"
    if lo < 60:
        return f"about 1-{max(2, round(hi / 60))} min"
    return f"about {int(lo // 60)}-{max(int(lo // 60) + 1, round(hi / 60))} min"
