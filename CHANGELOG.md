# Changelog

## Unreleased

- **Parallel cleaning and aligning:** a view that has to be built cleans and aligns its frames in
  `SPHEREX_WORKERS` processes (default min(CPUs, 8)): a cold Barnard's Star view (61 frames)
  2.2 -> 0.6 s, all six detectors (197 frames) 6.4 -> 1.8 s, with the workers already running
  (the app starts them when a target is shown). Same results for any number of workers.
- **Frame cache:** every image, once cleaned and aligned onto a view's grid, is kept in
  `<cache>/frames_proc/`, so a view that shares images with an earlier one (clip on/off,
  another time step, another detector combination on the same grid) skips that work. Stacks are
  byte-identical with it on or off. Capped at 2 GB, least recently used first
  (`SPHEREX_FRAME_CACHE_MAX_GB`); `SPHEREX_FRAME_CACHE=0` turns it off; `paramost cache-info`
  shows it and `paramost cache-clear frames` empties it.

## v1.0.0 (2026-11-16)

The first release of the SPHEREx Flipbook, built for the NASA Space Apps Challenge 2026
(Planet X and SPHEREx) between 2026-11-10 and 2026-11-16. It is installable as `paramost`
(with pipx or Docker) and includes the `spherex` library.

### The app
- Type a name or coordinates (decimal degrees or sexagesimal, with or without `RA`/`Dec`
  labels and a comma) and see one picture per SPHEREx visit.
- **Video player:** play, pause, step and a slider, or an animated GIF, in three modes:
  normal, difference and minus-mean. Time steps run per visit, monthly, weekly or every frame.
  The player can show real time gaps, and you can choose which pictures to include.
- **Pictures:** single visit, deep, pair difference (always later minus earlier, with both
  visits picked by date), band difference, RGB, combined detectors (`D5+D6`, `all`) and
  wavelength ranges.
- **Overlays:** Gaia DR3 and CatWISE2020, moved to the picture's date, with proper-motion
  arrows and a catalogue check of the target. SkyBoT asteroids, and an optional Aladin Lite
  sky viewer.
- **Light curves:** at one wavelength (±0.02 µm), grouped by visit, with one marker per data
  release, each point's wavelength and lower limits for saturated stars. Warnings cover
  saturation, neighbours in the measuring circle, mixed releases, wavelength spread and wide
  windows.
- **Spectra:** for the latest visit or every visit, binned into the 102 channels, with CSV
  export.
- Flags view, visits table, a glossary and explanations.
- **Links and help:** coordinate links that open any view from the URL, one-line help texts,
  and the data releases used plus a "data as of" date under the video.
- **Live by default, with an Offline toggle.** The app says how many images a view needs
  before downloading anything, shows a progress bar with time left, and gives friendly
  messages when a target is "not downloaded yet" or the archive is not answering.
- **Your targets:** buttons on the start screen for the targets you have downloaded, with
  remove (after a confirmation) and a background preload of the most recent ones. A new
  install starts on an empty start screen.

### The library (`spherex`)
- **`spherex.api`:** one call per view (`resolve`, `visits`, `epochs`, `flipbook`,
  `player_html`, `picture`, `overlay_figure`, `light_curve_figure`, `spectrum_figure`,
  `flags_figure`, `molecule_bands`, `count_downloads`, `defaults`), documented in
  `docs/API.md`.
- **Releases:** SPHEREx releases are read from IRSA; DR is used before QR, newer before older.
- **Flags:** both FLAGS header formats are read, `MP_` (QR2) and `MSKN` (QR3/DR1), with a
  fallback to the Explanatory Supplement's bit numbers.
- **Saturated stars:** handled for pictures and stacks; their measurements are lower limits.
- **Stacking:** sigma-clipped (4 sigma, median/MAD) where 4 or more frames cover a pixel, and
  median for 2-3. `n_min`, `clipped_fraction` and "few frames: unreliable" mark weak pictures,
  and `clip=False` keeps the plain average.
- **Proper motion:** positions use each target's catalogue epoch (WISE 0855: 2010.4).
  Typed coordinates near a known target pick up its motion.
- **Faster downloads:** up to 6 at once (`SPHEREX_DOWNLOAD_WORKERS`) with atomic writes;
  62 images took 110 s instead of 799 s. The PSF layer is dropped, so cutouts are 93% smaller.
- **Saved results:** stacks, light curves and spectra are kept in `<cache>/results/`, keyed by
  every setting and the exact frame list. They are identical to a fresh computation, and
  WISE 0855 opens in 3.4 s instead of 11.3 s.
- **Bounded image cache:** `SPHEREX_CACHE_MAX_GB`, `SPHEREX_CACHE_POLICY` (`evict`/`stop`) and
  `SPHEREX_CACHE_TTL_DAYS`.
- An optional progress callback with time-left estimates.

### Install and run
- **`paramost` command:** `--port`, `--address`, `--offline`, `--cache-dir`, `--no-browser`,
  `cache-info` and `--version`. `python -m paramost` works too.
- **Cache folder:** `SPHEREX_CACHE`, else an existing `cache/` in a source checkout, else the
  user cache folder (`~/.cache/paramost` on Linux). An existing cache is never moved.
- **Docker image** (`python:3.12-slim`, non-root, `/data/cache` volume, health check),
  published to `ghcr.io/utmos12345/paramost` on version tags.
- **CI:** tests on Python 3.11 and 3.12 for every push and pull request.
- **Self-hosting:** systemd, nginx and cron files in `deploy/`, with `docs/deploy.md`. There
  is no public instance.

### Documentation
- **README:** results on the five challenge targets, with their limits.
- **Gallery** (`docs/index.html`, for GitHub Pages) and a tutorial notebook
  (`notebooks/tutorial.ipynb`).
- **Project files:** CONTRIBUTING, ROADMAP, issue templates, a BSD-3-Clause license and
  CITATION.cff.

### Known limits
- **Saturated stars** (Barnard's Star, R Draconis, partly RW Aur) have no data in their cores;
  their brightnesses are lower limits.
- **Neighbours:** only Gaia stars inside the 12″ measuring circle are reported. WISE 0855 has
  a G = 16.3 neighbour 4-6″ away.
- **Sparse light curves:** 1-5 points per target. Mixed DR1/QR3 calibration can differ by
  several percent.
- **Clipping hides short events:** it suppresses sources seen in only a minority of a visit's
  frames. Use `clip=False` or weekly pictures to find them.
- **Downloads:** the first view of a new target takes about 1-3 minutes.
