# SPHEREx Flipbook

NASA Space Apps Challenge 2026, "Planet X and SPHEREx".

Type a sky position (RA and Dec, or a name) and see the SPHEREx images of that patch of sky
as a little video, one picture per SPHEREx visit, so that anything that moved or changed
brightness stands out. Around the video: difference pictures, colour pictures from the six
detectors, Gaia DR3 and CatWISE2020 overlays with proper-motion arrows, light curves, spectra
measured on the fly from all 102 SPHEREx channels, and the contamination flags of the data.

The data side is the Python package `spherex/`; `spherex/api.py` is the interface the web app
calls (see `docs/API.md`). `paramost/app.py` is the Streamlit web app; `paramost` starts it.

## How it meets the challenge

- **Core: RA/Dec in, a video of that patch out.** Names, decimal degrees and sexagesimal
  (`08h55m10.831s -7d14m42.53s`, also `RA 08h55m10.831s, Dec -7d14m42.53s`) are accepted.
  Every visit is stacked onto one fixed sky grid, so a moving object changes position between
  pictures. A green circle shows where the target should be on each date, using its proper
  motion. A new position downloads its images from IRSA first (about 1-3 min for a video);
  after that it opens from the cache.
- **1. Easy to update with new data releases.** The list of SPHEREx releases is read from
  IRSA each time a new target is searched; new Quick Releases (QRn) and Data Releases (DRn)
  are picked up without code changes, and when an exposure is in several releases the best
  one is used (DR before QR, newer before older). `api.visits(text, refresh=True)` searches
  again for a cached target.
- **2. The 102 bands, combined detectors, spectra on the fly.** Pictures from one detector,
  a sum of detectors (`D5+D6`, `all`), or a wavelength range (`4.4-4.7` µm); a colour picture
  (D6, D3, D1 as red, green, blue); a "band difference" (D6 minus scaled D2) in which ordinary
  stars cancel and cold objects remain. Spectra are measured from the images when asked:
  each frame sees the target at its own wavelength, and the measurements are averaged into
  the 102 channels, for the latest visit or for every visit.
- **3. Adding and subtracting images taken at different times.** All visits added (deep
  picture); latest minus first visit; a video of each visit minus the first; a video of each
  visit minus the average of the others (only changes remain).
- **4. User-chosen field of view.** 1 to 10 arcmin.
- **5. Overlays from other telescopes.** Gaia DR3 and CatWISE2020 sources moved to the date of
  the picture, with arrows for significant proper motions (CatWISE motions only at ≥ 5 sigma
  and without artefact flags). Known asteroids from IMCCE SkyBoT when that service is reachable.
- **6. Coordinates in the URL.** The app reads and writes `?target=...&detector=...&fov=...`.
- **7. Metadata such as contamination flags.** A flags view shows one exposure as observed and
  as cleaned, with every flag and the share of pixels that carry it; light-curve tables list the
  flags inside the measuring circle and the data release of each point; the visits table lists
  frames per detector and releases per visit.
- **8. Public tools.** Astropy (coordinates, WCS, time, FITS, statistics), astroquery (IRSA,
  Gaia, SIMBAD, SkyBoT), reproject and photutils. Aladin Lite (CDS) is used only for the optional sky viewer.

## Install

**With pipx** (recommended: the app gets its own environment and a `paramost` command):

```
pipx install git+https://github.com/UTMOS12345/spherex_project.git
paramost
```

`paramost` opens the app in your browser at http://localhost:8501. Python 3.10 or newer; the
newest dependency versions need 3.12.

**With Docker** (nothing to install besides Docker):

```
docker build -t paramost .                                     # or, once v1.0.0 is published:
docker run -p 8501:8501 -v paramost-cache:/data/cache paramost   # ghcr.io/utmos12345/paramost:1.0.0
```

then open http://localhost:8501. Downloads stay in the `paramost-cache` volume.

**From a source checkout** (to change the code):

```
python -m venv .venv
.venv/bin/pip install -e ".[test]"        # or: pip install -r requirements.txt (exact versions)
.venv/bin/python -m paramost
```

Options: `paramost --port 8502`, `--no-browser`, `--offline`, `--cache-dir PATH`,
`paramost cache-info` (where the cache is, how big, which targets), `paramost --version`.

## First run

A new install starts with an empty screen: a search box and one line, "Type a star name or
coordinates. The first view downloads from NASA's archive (about 1-3 min); after that it opens
instantly." Nothing is downloaded until you ask:

1. Type a name (`WISE 0855`, `Barnard's Star`) or coordinates (`133.795 -7.245`,
   `08h55m10.8s -07d14m42.5s`).
2. The archive is searched for SPHEREx frames of that position, and the view says how many images
   it needs, for example "this view needs 62 images from IRSA that are not downloaded yet
   (about 1-3 min)", with a **download** button. Nothing starts before you press it; a progress
   bar with the time left runs while it downloads (6 images at a time).
3. The result (stacked visits, light curve, spectrum) is saved in the cache, so the same view
   opens instantly the next time, also after restarting the app.

Targets you have downloaded appear on the start screen under **your targets**, newest first,
with the date you last looked and their size on disk. A button opens the target with the
settings you last used; **remove** (after a confirmation) deletes its images and saved
results.

## Offline mode

The **Offline** toggle at the top (or `paramost --offline`, or `?offline=1` in the link) uses
only data already on this computer: nothing is downloaded, and a target without images says
"Not downloaded yet". Turn it off to download. A server for a public demo sets
`SPHEREX_DEMO=1`, which starts the app offline and hides the remove buttons (see
[docs/deploy.md](docs/deploy.md)).

## Where the cache lives

Everything downloaded or computed (images, frame lists, catalogue cones, saved results and the
`targets.json` index behind "your targets") lives in one folder:

| installed with | cache folder |
|---|---|
| pipx / pip on Linux | `~/.cache/paramost` |
| pipx / pip on macOS | `~/Library/Caches/paramost` |
| pipx / pip on Windows | `%LOCALAPPDATA%\paramost\Cache` |
| Docker | `/data/cache` in the container (the volume) |
| a source checkout | `cache/` in the checkout (an existing cache is never moved) |

`paramost --cache-dir PATH` or `SPHEREX_CACHE=PATH` uses another folder; `paramost cache-info`
prints the folder and its size. A target's images take about 0.4 MB each, so a target with 60
to 120 images needs 25-50 MB. The cache can be capped:

- `SPHEREX_CACHE_MAX_GB` (float, unset = unlimited): size cap over the downloaded images.
- `SPHEREX_CACHE_POLICY` (`evict` default | `stop`): `evict` deletes the least recently used
  images after new downloads to stay under the cap; `stop` never deletes and refuses new
  downloads when full.
- `SPHEREX_CACHE_TTL_DAYS` (float): delete images older than this many days.
- `SPHEREX_DOWNLOAD_WORKERS` (default 6): images downloaded at once.

## Uninstall

```
pipx uninstall paramost
```

and delete the cache folder from the table above (for example `rm -rf ~/.cache/paramost`) to
free the disk space. With Docker: `docker rm` the container, `docker volume rm paramost-cache`
and `docker rmi paramost`.

## What works (verified on cached data of the five test targets)

- Target lookup: the five test targets by name and common aliases; decimal degrees and
  sexagesimal coordinates, with or without `RA`/`Dec` labels and a comma. Coordinates within
  10″ of a test target's catalogue, Gaia DR3 (2016.0) or present-day position use its proper
  motion.
- Frame search results merged across DR1 and QR3; cutouts read from the cache.
- Cleaning: ZODI subtraction and masking of flagged pixels (both FLAGS header formats).
- Stacking each visit onto one sky grid. Where 4 or more frames cover a pixel, a sigma-clipped
  mean (4 sigma, median centre, MAD spread) rejects values that disagree with the other frames,
  so a single bad frame cannot create a fake source; where 2 or 3 frames cover it, the median;
  one frame is used as it is. Each visit reports `n_min` (fewest frames under the centre of the
  picture) and `clipped_fraction` (share of values rejected, 1-4% on the test targets); pictures
  from fewer than 4 frames are titled "few frames: unreliable". `clip=False` gives the plain
  average of the frames instead (identical to the stacks before the clipping was added).
- The video as an animated GIF and as an interactive player page (play, pause, step, slider),
  in three modes: normal, difference (each visit minus the first), minus-mean.
- Pictures: one visit, deep (all visits), pair difference (always the later visit minus the
  earlier: red = brighter later, blue = brighter earlier), band difference (red = brighter in D6,
  blue = brighter in scaled D2), RGB.
- Combined detectors (`D5+D6`, `all`) and wavelength-range pictures (`4.4-4.7`).
- Gaia DR3 and CatWISE2020 overlays with proper-motion arrows and a catalogue check of the target.
- Light curve at one wavelength: one average per SPHEREx visit, one marker per data release, each
  point labelled with the wavelength it was measured at, lower limits for saturated stars, and
  warnings for saturation, neighbouring stars in the measuring circle, mixed data releases,
  points measured at different wavelengths, and wide wavelength windows.
- Spectrum of the latest visit and of every visit, with lower limits only for saturated
  measurements (a mostly masked measuring circle is shown as "masked: not measured"), and a
  mixed-release note on the every-visit spectrum.
- Flags view and visits table.
- Offline (demo) mode: every view above runs with the network switched off.

In the code but not verified here: the asteroid overlay (needs IMCCE SkyBoT online) and
`refresh=True`.

## The five test targets

- **Barnard's Star** (3 visits, Aug 2025 to Sep 2026). The fastest-moving star in the sky: in the
  difference video it leaves a clear red/blue pair, and the green circle follows it about 11″ in
  a year. It is saturated in SPHEREx, so its light curve and spectra are lower limits.
- **Epsilon Indi B** (4 visits). A nearby brown-dwarf pair moving about 4.7″ per year; the motion
  pair is clear in the difference picture at 4.2 µm. Its light curve rises 10% in the last visit.
  The step coincides with the change from DR1 to QR3 data, but it is explained by wavelength: the
  last point was measured at 4.195 µm, the earlier ones at 4.211 and 4.213 µm, on a steep part of
  the spectrum. At matched wavelengths the two releases agree within about 2%. The figure shows
  each point's wavelength and warns about both the spread and the mixed releases.
- **WISE 0855** (3 visits, all DR1). The coldest known brown dwarf, faint and only seen at 4-5 µm.
  The CatWISE overlay shows its 8″ per year motion. A G = 16.3 star lies 4-8″ away, inside the
  measuring circle: its spectrum below about 3 µm is that star, and its light curve is affected.
  The figures carry this warning and name the neighbour as the main light source where WISE 0855
  is faint. Its first visit has only 3 frames, so pictures that use it are marked
  "few frames: unreliable".
- **RW Aur** (3 visits). A young variable star: brighter by about 50% at 0.9 µm in the last visit
  than in the first two. Field stars in the same frames stay within 1-3%, so the change is real.
- **R Draconis** (6 visits; D3 images in 3 of them). A pulsating red giant, saturated in every
  channel measured: the pictures show a filled core, the light curve has a single lower limit, and the
  difference video shows the brightness change only in the star's wings.

## Known limits

- **Saturated stars** (Barnard's Star, R Draconis, partly RW Aur): their cores have no data and
  are filled from the surrounding pixels in pictures; brightnesses are lower limits.
- **Neighbouring stars**: SPHEREx pixels are 6.15″ and the measuring circle is 12″ in radius.
  Gaia stars inside it are reported; stars only bright in the infrared are not checked.
- **Mixed data releases**: light curves and per-visit spectra can combine DR1 and QR3 frames,
  whose calibration can differ by several percent. Both say so on the figure and in the warning.
- **Wavelength differences within a light curve**: each point is measured where the target falls
  within ±0.02 µm of the chosen wavelength, so points can differ by up to 0.04 µm. On a steep
  spectrum that alone changes the flux by several percent (Epsilon Indi B: about 10%). The figure
  labels every point's wavelength and warns when they differ by more than 0.01 µm.
- **Stacking hides short events**: the sigma clipping suppresses sources that are in only a
  minority of a visit's frames: an asteroid moving about one pixel (3″) per frame keeps about a
  third of its light, a flare seen in 6 of 21 frames about three quarters. `clip=False` (plain
  average) or weekly pictures (`days=7`) show them, along with any single-frame defects.
- **Few frames**: with 2 frames per pixel the median is the mean of the two, so a bad value still
  shows; pictures resting on fewer than 4 frames are marked "few frames: unreliable".
- **Sparse light curves**: a light curve uses only frames where the target falls within
  ±0.02 µm of the chosen wavelength, so a target has 1-5 points.
- **First view of a new target**: searching IRSA and downloading 50-120 images takes about 1-3
  minutes (6 at a time; one at a time took 13 minutes for 62 images). When IRSA does not
  answer, the app says so and tries again on the next request.
- **Field of view** up to 10′ (larger views would need bigger downloads).
- **Runs on your computer**: the app is meant to be installed locally; a hosted demo is
  optional (docs/deploy.md).

## Data and credits

This tool uses:
- SPHEREx data from the NASA/IPAC Infrared Science Archive (IRSA), operated by Caltech/IPAC under
  contract with NASA.
- Gaia DR3 from the ESA mission Gaia, processed by the Gaia Data Processing and Analysis
  Consortium (Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1), via IRSA and the ESA Gaia archive.
- CatWISE2020 (Marocco et al. 2021, ApJS 253, 8), via IRSA.
- SIMBAD, operated at CDS, Strasbourg (Wenger et al. 2000), and the CDS Sesame name resolver.
- Aladin Lite (CDS, Strasbourg), for the optional sky viewer around the target.
- SkyBoT, IMCCE, Observatoire de Paris (Berthier et al. 2006).
- Astropy, astroquery, reproject, photutils, NumPy, SciPy, Matplotlib, Streamlit and platformdirs.

## Files

- `spherex/` the library; `spherex/api.py` the functions the app calls (`docs/API.md`).
- `paramost/` the app: `app.py` (Streamlit), `cli.py` (the `paramost` command), `index.py`
  (the "your targets" index). `app.py` at the root only forwards to it, for servers whose
  systemd unit still starts `app.py`.
- `tools/` command-line scripts for a source checkout (docs/deploy.md): `prepare_demo.py`,
  `make_gallery.py`, `explore.py`, and `strip_psf.py IN OUT`, which writes copies of old
  cutouts without their unused PSF layer (93% smaller).
- `docs/` `API.md` (the library interface), `deploy.md` (hosting a demo server);
  `docs/history/` earlier review notes.
- `tests/` unit tests (`pip install -e ".[test]"`, then `pytest`; no network needed).
- `cache/` in a source checkout: the frame lists and catalogue cones of the five test targets
  (tracked) and whatever you download (not tracked).
- `deploy/` systemd unit, nginx site, bootstrap and auto-deploy scripts for a server.
- `Dockerfile`, `.github/workflows/` (tests on Python 3.11 and 3.12; the image on v* tags).
