# Roadmap

Six next steps after v1.0.0. Each one is written as a GitHub issue: copy the title and the body.
Items 2, 3 and 4 are done (see the note under each).

---

### 1. Blind search for moving objects in a field

**Title:** Blind search for moving objects in a field (difference image + source detection + catalogue cross-match)

**Body:**

Today the app looks at a target you name. A blind search would find moving or changing
sources in a whole field without being told where to look.

Proposed steps:
1. Build a difference image of two visits (`api.picture(kind="pair")` already makes one on a
   common sky grid) or the minus-mean stack.
2. Detect sources in it (for example `photutils.segmentation` or DAOStarFinder on the positive
   and the negative image separately), with a noise threshold from the stack's spread.
3. Pair positive and negative detections whose separation fits a plausible proper motion.
4. Cross-match the pairs with Gaia DR3 and CatWISE2020 (`spherex/gaia.py`, `spherex/wise.py`),
   moved to the epochs of the two visits. Report the pairs that match no known moving source.

Watch out for:
- saturated stars, whose filled cores leave residuals;
- the few-frames visits;
- mixed releases;
- the sigma clipping, which suppresses sources seen in only part of a visit (`clip=False`
  keeps them).

Done when: `api.find_movers(text, fov, ...)` returns a table of candidates with positions,
motion and catalogue matches, and the five challenge targets come back as known movers where
they move.

---

### 2. Cache cleaned and reprojected frames

**Done:** merged in c7387d8 (`frame-cache` branch, tag `before-framecache` marks the state before it): `spherex/framecache.py`, size cap with LRU eviction, `SPHEREX_FRAME_CACHE=0` turns it off.

**Title:** Cache cleaned and reprojected frames so repeat views with other settings are instant

**Body:**

Saved results (`spherex/results.py`) make an *identical* repeat view instant. A view with one
setting changed (field of view, time step, clip on or off) still cleans and reprojects every
frame again.

Proposal: save each frame after cleaning and reprojection onto the target's sky grid. Key it
like the other results, by:
- the frame URL,
- the grid (target position, field of view, pixel scale),
- the `keep_saturated_stars` setting,
- the spherex and RESULTS versions.

Stacking with another time step or clip setting would then only re-run the combine step.

Points to settle:
- disk use per frame (float32 arrays of the grid size);
- eviction, together with `SPHEREX_CACHE_MAX_GB`;
- whether a frame is saved only once all frames of the view are present (the rule saved
  results follow today).

Done when: changing the time step or clip on a cached target needs no cleaning or reprojection,
and the outputs stay identical to a fresh computation (the test in `tests/test_results.py` is
the model).

---

### 3. Multiprocessing across frames for clean/reproject

**Done:** merged in db019c5 (`speed` branch, commit 14f3728; tag `before-speed` marks the state before it): `spherex/workers.py`, `SPHEREX_WORKERS`, stacks identical for 1 and N workers.

**Title:** Use several CPU cores for cleaning and reprojecting frames

**Body:**

Cleaning (`spherex/clean.py`) and reprojection (reproject) run one frame after another. On a
new target with 100+ frames, this is the slowest step after the download.

Proposal: a `concurrent.futures.ProcessPoolExecutor` over frames in `spherex/epochs.py`, with:
- `SPHEREX_WORKERS` (default: cores - 1; 1 = today's behaviour);
- results gathered in frame order, so stacks stay byte-identical;
- small payloads: pass paths and the grid WCS header, not arrays;
- a fallback to serial when processes cannot be started (Streamlit, Windows spawn).

Done when: a benchmark on one target shows the speed-up, and stacks are identical for 1 and N
workers (like `tests/test_parallel_download.py` for downloads).

---

### 4. Adaptive download concurrency with backoff on 502/503

**Done:** merged in db019c5 (`speed` branch, commit 2b2a135): `spherex/throttle.py`, halving on 429/502/503/504 and timeouts, Retry-After, one keep-alive session.

**Title:** Adaptive download concurrency with backoff when IRSA answers 502/503

**Body:**

Downloads run six at a time (`SPHEREX_DOWNLOAD_WORKERS`). When IRSA is overloaded it answers
502/503, and the search services (TAP/SIA) have stayed at 502 for hours while the cutout
service worked. Each request then retries on its own.

Proposal:
- Treat 502/503/429 as "slow down": halve the number of workers (minimum 1), and wait with
  exponential backoff plus jitter. Honour `Retry-After` when it is present.
- After a run of successes, add workers back one at a time, up to the configured maximum.
- Show the state in the progress bar ("IRSA is busy: downloading 2 at a time").
- Stop with the existing "archive not answering" message after a total deadline.

Done when: a test with a fake server that returns 503 for a while shows fewer workers, no
failure, and identical files, and a healthy server still gets the full concurrency.

---

### 5. A scriptable CLI for batch rendering

**Title:** `paramost render`: a scriptable command for batch rendering

**Body:**

Everything the app shows can be made from Python (`spherex.api`). Scripts and pipelines would
be simpler with a command, for example:

```
paramost render "WISE 0855" --detector D6 --fov 4 --out wise0855/ \
    --products video,difference,overlay,light-curve,spectrum
paramost render --targets targets.txt --out gallery/ --offline
```

Requirements:
- each product written as PNG/GIF, plus CSV for the tables, and a JSON summary with the
  warnings;
- `--offline` uses only the cache; without it, a count of the images to download first;
- the exit code says whether every product was made.

`tools/make_gallery.py` and `tools/prepare_demo.py` already do part of this, for the five
challenge targets only, and could become thin wrappers.

Done when: the docs/ gallery can be rebuilt with one command.

---

### 6. Split `spherex/` into its own installable library

**Title:** Publish `spherex/` as its own installable library

**Body:**

`spherex/` is already independent: it never imports from `paramost/` or `tools/`. But it ships
only inside the `paramost` package, with Streamlit as a dependency.

Proposal:
- A separate distribution (name to check on PyPI, since `spherex` may be taken), with its own
  `pyproject.toml`, version and changelog.
- Dependencies without Streamlit.
- `paramost` would then depend on it.

Open questions:
- the cache location (`platformdirs` name `paramost` today);
- `matplotlib.use("Agg")` at import, which a library should not force;
- which functions of `spherex.api` are the public, stable interface.

Done when: `pip install <name>` gives `from spherex import api` without Streamlit, and the app
works unchanged on top of it.
