# SPHEREx Flipbook

NASA Space Apps Challenge 2026, "Planet X and SPHEREx".

Type a sky position (RA and Dec, or a name) and see the SPHEREx images of that patch of sky
as a little video, one picture per SPHEREx visit, so that anything that moved or changed
brightness stands out. Around the video: difference pictures, colour pictures from the six
detectors, Gaia DR3 and CatWISE2020 overlays with proper-motion arrows, light curves, spectra
measured on the fly from all 102 SPHEREx channels, and the contamination flags of the data.

The data side is the Python package `spherex/`; `spherex/api.py` is the interface the web app
calls (see `API.md`). `app_example.py` is the Streamlit web app.

## How it meets the challenge

- **Core: RA/Dec in, a video of that patch out.** Names, decimal degrees and sexagesimal
  (`08h55m10.831s -7d14m42.53s`, also `RA 08h55m10.831s, Dec -7d14m42.53s`) are accepted.
  Every visit is stacked onto one fixed sky grid, so a moving object changes position between
  pictures. A green circle shows where the target should be on each date, using its proper
  motion. The five test targets are cached and run offline; any other position downloads its
  images from IRSA first (minutes).
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
  Gaia, SIMBAD, SkyBoT), reproject and photutils. Aladin (CDS) is not used.

## Install and run

Tested with Python 3.14. Run the commands from this folder.

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install streamlit                   # for the web app only
SPHEREX_DEMO=1 .venv/bin/streamlit run app_example.py
```

`SPHEREX_DEMO=1` (or `api.set_demo_mode(True)` in code) is the setting for a live demo: no
downloads, and every server call gets one short try, so nothing can hang; images not in
`cache/` are skipped. Without it, new targets are downloaded from IRSA.

`cache/` (about 3 GB of cutouts, plus frame lists and catalogue cones) is found next to the
`spherex/` package whatever folder Python starts in; set `SPHEREX_CACHE=/path` to use another.

Backup results for the five test targets, made from the cache:

```
SPHEREX_DEMO=1 .venv/bin/python prepare_demo.py --skip-explore    # video, difference, overlay, light curve, spectrum
.venv/bin/python make_gallery.py                                  # every other product, demo/STATUS.md, demo/index.html
```

Open `demo/index.html` to see them all. Note: `make_gallery.py` downloads the images a product
needs when the cache has none of them (it switches demo mode off for that step).
`prepare_demo.py --refresh` searches IRSA for new data and `--all-frames` downloads every frame;
both need the network and take long.

## What works (verified on the cached data of all five targets)

- Target lookup: the five test targets by name and common aliases; decimal degrees and
  sexagesimal coordinates, with or without `RA`/`Dec` labels and a comma. Coordinates within
  10″ of a test target's catalogue, Gaia DR3 (2016.0) or present-day position use its proper
  motion.
- Frame search results merged across DR1 and QR3; cutouts read from the cache.
- Cleaning: ZODI subtraction and masking of flagged pixels (both FLAGS header formats).
- Stacking each visit onto one sky grid with a sigma-clipped mean, so a single bad frame
  cannot create a fake source.
- The video as an animated GIF and as an interactive player page (play, pause, step, slider),
  in three modes: normal, difference (each visit minus the first), minus-mean.
- Pictures: one visit, deep (all visits), pair difference, band difference, RGB.
- Combined detectors (`D5+D6`, `all`) and wavelength-range pictures (`4.4-4.7`).
- Gaia DR3 and CatWISE2020 overlays with proper-motion arrows and a catalogue check of the target.
- Light curve at one wavelength: one marker per data release, lower limits for saturated stars,
  and warnings for saturation, neighbouring stars in the measuring circle, mixed data releases
  and wide wavelength windows.
- Spectrum of the latest visit and of every visit, with lower limits for saturated stars.
- Flags view and visits table.
- Offline (demo) mode: every view above runs with the network switched off.

In the code but not verified here: the asteroid overlay (needs IMCCE SkyBoT online), searching
and downloading new targets, `refresh=True`, and the Streamlit app itself (URL parameters, the
player inside the page).

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
  The figures carry this warning.
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
  whose calibration can differ by several percent. Light curves mark this; per-visit spectra do not.
- **Sparse light curves**: a light curve uses only frames where the target falls within
  ±0.02 µm of the chosen wavelength, so a target has 1-5 points.
- **Slow first load for new targets**: searching IRSA and downloading 50-70 cutouts, one after
  another, takes several minutes before the first video. The five test targets are cached.
- **Field of view** up to 10′ (larger views would need bigger downloads).
- **Not publicly hosted**: the tool runs locally with the cache next to it.

## Data and credits

This tool uses:
- SPHEREx data from the NASA/IPAC Infrared Science Archive (IRSA), operated by Caltech/IPAC under
  contract with NASA.
- Gaia DR3 from the ESA mission Gaia, processed by the Gaia Data Processing and Analysis
  Consortium (Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1), via IRSA and the ESA Gaia archive.
- CatWISE2020 (Marocco et al. 2021, ApJS 253, 8), via IRSA.
- SIMBAD, operated at CDS, Strasbourg (Wenger et al. 2000), and the CDS Sesame name resolver.
- SkyBoT, IMCCE, Observatoire de Paris (Berthier et al. 2006).
- Astropy, astroquery, reproject, photutils, NumPy and Matplotlib.

## Files

- `spherex/` the library; `spherex/api.py` the functions the app calls (`API.md`).
- `app_example.py` the Streamlit app.
- `prepare_demo.py`, `make_gallery.py` fill `demo/` with backup results; `explore.py` writes extra
  products to `out/`.
- `lesson*.py`, `show_target.py` step-by-step scripts used while building the library.
- `cache/` frame lists, cutouts, Gaia and CatWISE cones.
