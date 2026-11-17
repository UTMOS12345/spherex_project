# spherex.api: guide for the web app

The app only needs `from spherex import api, set_style`. `cache/` is found next to the
`spherex/` package wherever Python starts (`SPHEREX_CACHE=/path` overrides it). The working example
is the app itself, `paramost/app.py` (`python -m paramost`).

## For the app

- **Turn demo mode on at start** for a server open to visitors: `api.set_demo_mode(True)` (or start with
  `SPHEREX_DEMO=1`). Without it, any setting whose images are not in `cache/` downloads them from
  IRSA, which takes minutes, and on a bad network each image is retried for minutes more.
- **Show `table.meta["warning"]` on the page** (`st.warning(...)`) whenever a returned table has
  it. It explains saturation, neighbouring stars in the measuring circle, mixed data releases,
  wavelength differences between light-curve points and wide wavelength windows. The same text is
  drawn small at the bottom of the figure; that is not enough on its own.
- **Build visit pickers from `api.epochs(...)`, not from `api.visits(...)`**: called with the same
  settings as the picture or video (including `days`), its row i is exactly `visit=i` of `picture`
  and `overlay_figure` and frame i of the video, while `api.visits` also lists visits that have no
  picture for that detector.
- **Offer a time step** from `api.TIME_STEPS` and pass the same `days` to `player_html`,
  `flipbook`, `epochs`, `picture` and `overlay_figure`; pass the same `pictures` list to
  `player_html`, `flipbook` and `epochs`. Put `days` and `pictures` in every cache key
  (`st.cache_data` arguments) that involves these functions, or a cached video will not match its
  picker. Show `epochs(...).meta` as "N pictures from M frames" (and how many are few-frames), and
  for "every frame" say why the brightness flickers (see "Pictures, frames and speed").
- **Use `api.defaults(text)`** for the per-target detector, light-curve wavelength and tolerance.
  For the five test targets these are the settings already in `cache/`, and the function also
  recognises aliases and coordinates of those targets.
- **Offer a "raw average" switch** that passes `clip=False` to `flipbook`, `player_html` and
  `picture`. The default stacks reject values that disagree with the other frames of a visit; the
  raw average keeps everything, so fast movers and short flares that are in only a few frames show
  up (and so do single-frame defects).
- **Show the few-frames note.** Titles of pictures built from a visit with fewer than 4 frames
  under the centre end in "few frames: unreliable"; `overlay_figure` notes have `few_frames`, and
  `visits(text, detector=...)` lists `n_min` per visit. Repeat it next to the picture when it is set.

## How a visit's picture is made (stacking)

Every frame of a visit is cleaned (ZODI subtracted, flagged pixels masked), levelled to zero sky
and resampled onto one fixed sky grid. Then, pixel by pixel:
- 4 or more frames: **sigma-clipped mean** (4 sigma, median centre, MAD spread). A value that
  disagrees strongly with the other frames (an unflagged hole, a hot pixel, a cosmic ray) is
  rejected, so one bad frame cannot create a fake source.
- 2 or 3 frames: **median**. With 3 frames one bad value is ignored; with 2 the median is the mean
  of the two, so a bad value still shows.
- 1 frame: that frame's value.

Each visit records `n_min`, the fewest frames under the central half of the picture (below 4 the
picture is marked "few frames: unreliable"), and `clipped_fraction`, the share of pixel values the
clipping rejected (typically 1-4% on the test targets).

**Limit:** a source present in only a minority of a visit's frames is suppressed by the clipping:
a fast asteroid that moves about one pixel (3″) between frames keeps about a third of its light in
the stack, and a flare seen in 6 of 21 frames about three quarters. Use `clip=False` (plain
average of the frames, as before the clipping was added) or weekly pictures (`days=7`) to look for
such sources. Constant stars, and stars whose brightness changes with wavelength across a detector,
are not affected.

## Pictures, frames and speed

- A **frame** is one SPHEREx exposure of one detector (about 2 minutes apart within a visit). A
  **picture** is what the player shows at one step: the frames of one time step stacked into one
  image. **fps** (pictures per second) is only playback speed: it changes nothing in the pictures.
- The time step (`days`, `api.TIME_STEPS`) sets how long one picture may cover:

  | Step | `days` | Pictures (test targets, default detector) | Trade-off |
  |---|---|---|---|
  | per visit | 60 | 3-4 | deepest, cleanest pictures; one per visit, about 6 months apart |
  | monthly | 30 | 3-6 | splits the longest visits; nearly as clean |
  | weekly | 7 | 5-11 | follows changes within a visit; fewer frames each, so noisier and more often "few frames" |
  | every frame | 0 | 45-91 | one exposure per picture: no stacking, no clipping |

- **Every frame** (`days=0`): each exposure is cleaned and resampled onto the same grid on its own,
  with no clipping; every picture is marked few-frames and its date includes the time. Brightness
  **flickers** from picture to picture because each frame sees the target at a slightly different
  wavelength (the wavelength changes across a SPHEREx detector), and single-frame defects are not
  removed. In exchange, fast movers such as asteroids, which the clipped stacks suppress, show up.
  Exposures taken at the same moment on paired detectors (D1+D4, D2+D5, D3+D6) form one picture.
  More than 150 pictures (`epochs.MAX_PICTURES`) raise `ValueError`: use weekly pictures or one
  detector. Cost on the test targets: stacks 3-5 s (as for the other steps), player 4-6 s and
  about 2 MB, GIF 15-20 s and 3-5 MB (per visit: player 0.2 s, GIF under 1 s).
- `pictures=[i, j, ...]` (`player_html`, `flipbook`, `epochs`): only those rows of
  `api.epochs(...)` for the same settings, in time order. "difference" subtracts the first chosen
  picture; "minusmean" averages only the chosen ones; difference modes need at least 2. With
  `pictures`, `epochs` returns only those rows (row k = frame k); its `index` column keeps the
  number in the full table, which is what `picture(visit=...)` takes.
- `real_time=True` (`player_html`): each picture stays on screen in proportion to the time gap to
  the next one, between 1 and `max_hold` (6) times the base interval 1/fps, the same rule as the GIF
  timeline; the last picture stays `max_hold` times. The player has a "real time gaps" checkbox to
  switch this while it plays.
- Pass the same `days` to `player_html`, `flipbook`, `epochs`, `picture` and `overlay_figure`, and
  the same `pictures` to `player_html`, `flipbook` and `epochs`; include both in cache keys.

## Settings

| Name | What it is |
|---|---|
| `api.set_demo_mode(on)` | `True`: no downloads; frames not in `cache/` are skipped; every server call gets one try with a 20 s deadline. Also set by the environment variable `SPHEREX_DEMO=1`. |
| `api.demo_mode()` | `True` when demo mode is on. |
| `api.count_downloads(fn, *args, **kwargs)` | dict `missing`, `total`: how many images the api call `fn(*args, **kwargs)` would download (and use), without downloading or measuring anything. A new target is searched on IRSA first. For picture kinds `banddiff` / `rgb` count `epochs()` per detector. 0 in demo mode. |
| `SPHEREX_WORKERS` | environment variable: how many processes clean and align frames when a view has to be built (default min(CPUs, 8); 1 = all in one process). Results are the same for any value. The processes start with the `spawn` method on every platform, are reused, and stop after 10 minutes without work; about 130 MB each. If they cannot start, the work is done in one process (logged once). |
| `SPHEREX_FRAME_CACHE` | environment variable: `0` turns the frame cache off (every image is cleaned and aligned again for every view). The frame cache (`spherex.framecache`, `<cache>/frames_proc/`) keeps each image cleaned and aligned onto a view's grid; stacks are byte-identical with it on or off. |
| `SPHEREX_FRAME_CACHE_MAX_GB` | environment variable: size cap of the frame cache (default 2; 0 = no cap). Least recently used entries are deleted first; `SPHEREX_CACHE_TTL_DAYS` applies too. `paramost cache-clear frames` empties it. |
| `SPHEREX_DOWNLOAD_WORKERS` | environment variable: how many cutouts download at once to begin with (default 6; 1 = one after another, always). One more is allowed after every full round of successes, up to `SPHEREX_DOWNLOAD_WORKERS_MAX`; an archive "busy" answer (HTTP 429/502/503/504, a timeout, a dropped connection) halves it (down to 1) and Retry-After pauses new requests (spherex.throttle). The progress line shows the current number and "archive busy". Results and file names are the same for any value. |
| `SPHEREX_DOWNLOAD_WORKERS_MAX` | environment variable: the most cutouts at once (default 12). |
| `api.defaults(text)` | dict `detector`, `band` (µm), `tol` (µm) for a target: the cached settings for the five test targets (`api.DEMO_DEFAULTS`), else `api.OTHER_DEFAULTS` (D2, 1.6, 0.02). |
| `api.MAX_FOV` | 10.0: the largest field of view in arcmin. |
| `api.TIME_STEPS` | `{"per visit": 60, "monthly": 30, "weekly": 7, "every frame": 0}`: labels and `days` values for a time-step picker. |
| `api.MAX_SAFE_TOL` | 0.05: light curves with a wider wavelength window get a warning. |
| `api.WL_SPREAD_UM` | 0.01: light curves whose usable points differ in wavelength by more than this get a warning. |
| `set_style(dark=False)` | from `spherex`: one look for every figure; call once, `dark=True` for a dark page. |

## Functions

| Feature | Call | Returns |
|---|---|---|
| Search box | `api.resolve(text)` | dict: `name`, `ra`, `dec` (degrees, catalogue position), `ra_hms`, `dec_dms`, `has_motion`, `pm_ra`, `pm_dec` (mas/yr), `known` (True for the five test targets, by name, alias or coordinates) |
| Visits | `api.visits(text, refresh=False, detector=None, fov=4.0, clip=True)` | table: `visit`, `first_date`, `last_date`, `n_frames`, `D1`..`D6` (frames per detector), `releases`; with `detector`, also `n_min` and `clipped_fraction` of that detector's stacks (this stacks the visits if needed) |
| Pictures index | `api.epochs(text, detector=None, fov=4.0, wl=None, days=60, clip=True, pictures=None, progress=None)` | table, one row per picture the other functions build for these settings, in their order: `index`, `visit` (the `api.visits` number most of its frames belong to), `date` (as in the titles; with time for `days=0`), `first_date`, `last_date` (of the frames used), `n_frames`, `n_min`, `clipped_fraction`, `few_frames`, `detectors_used`, `releases`; `meta`: `n_pictures`, `n_frames_total`, `n_few_frames` |
| Video (GIF) | `api.flipbook(text, detector="D2", fov=4.0, mode="normal", fps=3, wl=None, days=60, timeline=True, clip=True, pictures=None, progress=None)` | GIF bytes |
| Video (player) | `api.player_html(text, detector="D2", fov=4.0, mode="normal", fps=3, wl=None, days=60, width=700, clip=True, pictures=None, real_time=False, max_hold=6, show_real_time_toggle=True, progress=None)` | HTML string: the same pictures with play/pause, step, a slider and a "real time gaps" checkbox (hidden with `show_real_time_toggle=False`) (`streamlit.components.v1.html(html, height=...)`) |
| Pictures | `api.picture(text, kind="visit", detector="D2", fov=4.0, visit=-1, a=-1, b=0, wl=None, long="D6", short="D2", rgb="D6,D3,D1", clip=True, days=60, progress=None)` | figure |
| Overlays | `api.overlay_figure(text, detector="D2", fov=4.0, visit=-1, gaia=True, wise=True, asteroids=False, min_pm=50, arrow_years=5, days=60, progress=None)` | (figure, notes dict) |
| Light curve | `api.light_curve_figure(text, band=1.6, tol=0.02, progress=None)` | (figure, table) |
| Spectrum | `api.spectrum_figure(text, visit=-1, all_visits=False, progress=None)` | (figure, table) |
| Flags | `api.flags_figure(text, detector="D2", visit=-1, frame=0)` | (figure, table) |
| Molecule markers | `api.molecule_bands()` | list of dicts (plain data, no plotting); see "Molecule bands" |

Show a figure with `st.pyplot(fig)` and then `plt.close(fig)`; a table with
`st.dataframe(table.to_pandas())`; GIF bytes with `st.image(gif)`.

`api.epochs` uses the same stacks and memory cache as the pictures, so it never disagrees with
them and costs nothing once a video has been built (about 15 ms). Row i is `picture(..., visit=i)`,
the `a` / `b` of kind "pair", `overlay_figure(..., visit=i)`, and frame i of `flipbook` and
`player_html` in every mode, when they get the same `detector`, `fov`, `wl`, `clip` and `days`
(and, for the videos, the same `pictures`). `detector=None` means D2 unless
`wl` is given. Example: for R Draconis with D3 the rows are visits 0, 3 and 4 of `api.visits`
(D3 did not observe it in visits 1, 2 and 5).

## Inputs

- `text`: a name ("WISE 0855"), degrees ("133.795 -7.245"), or sexagesimal
  ("08h55m10.8s -07d14m42.5s", "08:55:10.8 -07:14:42.5", "08 55 10.8 -07 14 42.5"). The two parts
  may be separated by a comma and labelled: "RA 08h55m10.831s, Dec -7d14m42.53s",
  "RA=133.795129 Dec=-7.245147". Coordinates within 10″ of a test target's catalogue, Gaia DR3
  (2016.0) or present-day position are treated as that target, with its proper motion.
- `detector`: "D1".."D6", a combination "D5+D6" (also "5+6", "D5,D6"), or "all".
- `wl`: a wavelength range in micron, "4.4-4.7", between 0.75 and 5.0. With `wl`, `detector` may
  be `None` (the detectors covering the range are used).
- `fov`: picture width in arcmin, 1 to 10.
- `mode` (`flipbook`, `player_html`): "normal" (one picture per visit), "difference" (each visit
  minus the first), "minusmean" (each visit minus the average of the others).
- `days` (`epochs`, `flipbook`, `player_html`, `picture`, `overlay_figure`): the longest time one
  picture may cover: 60 = one picture per visit, 30 monthly, 7 weekly (more pictures, each from
  fewer frames: noisier, and more often "few frames"), 0 = one picture per exposure. See
  "Pictures, frames and speed".
- `pictures` (`epochs`, `flipbook`, `player_html`): a list of row numbers of `api.epochs` for the
  same settings; only those pictures are used.
- `real_time`, `max_hold` (`player_html`): hold each picture in proportion to the gap to the next.
  `show_real_time_toggle=False` hides the player's own checkbox, for an app that offers its own.
- `timeline` (`flipbook`): a time bar under the picture, and each picture stays on screen longer
  when the gap to the next is longer.
- `clip` (`flipbook`, `player_html`, `picture`, `visits`): True = the stacking described above;
  False = plain average of the frames.
- `kind` (`picture`): "visit" (visit number `visit`), "deep" (all visits added), "pair" (the later
  of visits `a` and `b` minus the earlier, whichever order they are given in; red = brighter later,
  blue = brighter earlier), "banddiff" (`long` minus scaled `short`, latest visit with both; red =
  brighter in `long`, blue = brighter in scaled `short`), "rgb" (`rgb` = "red,green,blue"
  detectors, latest visit with all three).
- Visit (picture) numbers: rows of `api.epochs` with the same settings; 0 = first, -1 = latest.
- `min_pm`, `arrow_years` (`overlay_figure`): sources faster than `min_pm` mas/yr get an arrow
  showing where they will be `arrow_years` later. CatWISE sources also need a motion measured at
  5 sigma or better and no artefact flag.
- `band`, `tol` (`light_curve_figure`): only frames where the target falls within `tol` micron of
  `band` are measured. Keep `tol` at 0.02 to 0.05: a wider window mixes wavelengths.

## Outputs in detail

`overlay_figure` notes: `drawn` (list: "gaia", "wise", "asteroids"), `failed` (list of
"name: error type" for catalogues that could not be reached; the figure still comes back),
`in_gaia`, `in_wise` (a source within 3″ of the target's position on that date),
`nearest_gaia_arcsec`, `nearest_wise_arcsec`, `wise_halo_stars` (bright stars around which WISE
motions were ignored), `asteroids_in_view` (when asked for), `n_min`, `few_frames` and
`clipped_fraction` of the visit shown, and `verdict`, present when both Gaia and WISE were drawn.
`verdict` is a catalogue check, not a detection, and says so.

`light_curve_figure` and `spectrum_figure` tables: every column, and how to draw each kind of
row, is in "Drawing your own charts" below. Both tables hold everything their figure draws.

`flags_figure` table: `flag`, `bit`, `percent_of_pixels`, `masked` (whether this tool masks
it), only flags present in that exposure. If the requested exposure is not in `cache/` in demo
mode, the next one of that visit that is cached is shown.

## Units

Read units from the returned object; do not hardcode them in the app. They may change in a
future version.

- `light_curve_figure` figure: x axis "date (UTC)", y axis "brightness (mJy)". Table: every
  column ending in `_mjy` has `.unit` mJy, `wavelength_um` has µm (`um`), `mjd` and `visit_mjd`
  have `d` (Modified Julian Date, days).
- `spectrum_figure` figure (one visit or `all_visits=True`): x axis "wavelength (µm)", y axis
  "brightness (mJy)". Table: `_mjy` columns mJy, `wavelength_um` and `channel_wavelength_um` µm
  (`um`), `mjd` `d`.
- `molecule_bands()`: wavelengths in micron (the `_um` in the key names).

In code: `fig.axes[0].get_xlabel()`, `fig.axes[0].get_ylabel()`, `str(table["flux_mjy"].unit)`
(`None` for unitless columns such as `detector` or `state`). `table.to_pandas()` drops the units,
so read them before converting.

## Molecule bands

`api.molecule_bands()` returns the absorption-band markers that `spectrum_figure` draws (dashed
lines labelled with the molecule), as plain data so an app can draw them on its own charts. One
dict per marker, sorted by wavelength:

```python
{"name": "H2O", "wavelength_um": 1.4, "label": "H2O"}
```

`name`: molecule; `wavelength_um`: approximate band centre (micron); `label`: the text the figure
draws next to the line. A band given as a range would also have `"wavelength_range_um": [low, high]`
(none today). The values come from `plots.MOLECULES`, the single source used for the figures.
They are for orientation only: real bands are broad and depend on temperature.

## Drawing your own charts

The tables from `light_curve_figure` and `spectrum_figure` (one visit, or `all_visits=True`)
hold every value their figures draw, so an app can draw its own charts from them. Each row is one
measurement: one exposure, measured in a 12″ circle at the target's position on that date.
Brightnesses are in milli-Jansky (mJy), wavelengths in micron (µm), times in Modified Julian Days.

### Columns shared by both tables

| Column | Meaning | Unit |
|---|---|---|
| `wavelength_um` | wavelength the target was seen at in this exposure (it depends on where it lands on the detector) | µm |
| `flux_mjy` | brightness; NaN when the measurement is saturated or masked | mJy |
| `err_mjy` | 1-sigma uncertainty of `flux_mjy`; NaN when `flux_mjy` is NaN | mJy |
| `flux_min_mjy` | lower limit for a saturated measurement (the true brightness is higher); NaN otherwise, and NaN if no limit could be measured | mJy |
| `detector` | SPHEREx detector, 1-6 | - |
| `mjd` | mid-exposure time | MJD (days) |
| `n_bad` | masked pixels inside the measuring circle | pixels |
| `saturated` | the star's core is saturated at this position | True/False |
| `bad_flags` | flags found inside the circle, e.g. "NONFUNC,DICHROIC"; empty if none | text |
| `ok` | usable: no masked pixel in the circle and not saturated | True/False |
| `masked` | most of the circle is masked: no value at all | True/False |
| `state` | one of `ok`, `saturated`, `masked`, `flagged` (see below) | text |
| `release` | data release of the exposure: "DR1", "QR3", ... | text |
| `visit` | SPHEREx visit number (0 = first), as in `api.visits` | - |

`state`: **ok** = usable point. **saturated** = no brightness; `flux_min_mjy` is a lower limit if
finite. **masked** = not measured. **flagged** = a value exists (`flux_mjy`), but some pixels in
the circle are masked, so it is not used.

### Light curve only (`light_curve_figure`)

| Column | Meaning | Unit |
|---|---|---|
| `date` | `mjd` as a date and time (UTC) | text |
| `visit_mjd` | time of the visit, where the visit average is drawn (mean of its rows' `mjd`) | MJD |
| `visit_flux_mjy` | mean `flux_mjy` of the visit's `ok` rows; NaN if it has none | mJy |
| `visit_spread_mjy` | standard deviation of those rows, or the single row's `err_mjy` when there is one; NaN if none | mJy |
| `visit_n_ok` | number of `ok` rows in the visit | - |

The `visit_*` columns repeat on every row of the same visit; take one row per `visit`.

### Spectrum only (`spectrum_figure`)

| Column | Meaning | Unit |
|---|---|---|
| `channel` | SPHEREx channel the measurement falls in, 1-17 within its detector (0 = outside the channel grid) | - |
| `channel_wavelength_um` | centre of that channel, where the channel average is drawn | µm |
| `channel_flux_mjy` | mean `flux_mjy` of the `ok` rows in that channel (same visit); NaN when no average is drawn | mJy |
| `channel_err_mjy` | uncertainty of that mean | mJy |
| `channel_n` | number of `ok` rows in the average; 0 when there is none | - |

With `all_visits=False` all rows have the same `visit`; with `all_visits=True` there is one set
per visit. The `channel_*` columns repeat on every row of the same channel and visit; take one row
per (`visit`, `detector`, `channel`). They are NaN for a saturated visit, which is shown as lower
limits only.

### How to draw each kind of row

Light curve (x = `mjd` or `date`, y = brightness):
- **Normal point** (`state` ok): a small point at `flux_mjy` with an error bar `err_mjy`, with one
  marker shape per `release`. The static figure labels each point with its `wavelength_um`.
- **Lower limit** (`state` saturated, `flux_min_mjy` finite): an upward triangle at
  `flux_min_mjy`, labelled "at least ..."; never join it to other points.
- **Not measured** (`state` masked) and **not used** (`state` flagged): no point. If a visit has
  no `ok` and no lower-limit row, mark the visit at the bottom as "no usable data".
- **Visit average** (one per `visit` with `visit_n_ok` >= 2): a large filled symbol at
  (`visit_mjd`, `visit_flux_mjy`) with an error bar `visit_spread_mjy`. Join these averages with a
  line, in time order.
- **Visit with a single measurement** (`visit_n_ok` = 1): a large open symbol, legend
  "single measurement", with its own error as the bar. Do not join it to other visits by a line:
  one exposure cannot support a trend.

Spectrum (x = `wavelength_um`, y = brightness, logarithmic when it spans more than 30x):
- **Normal point** (`state` ok): a small faint point at `flux_mjy` with error bar `err_mjy`.
- **Channel average** (rows with finite `channel_flux_mjy`, one per channel): a large point at
  (`channel_wavelength_um`, `channel_flux_mjy`) with error bar `channel_err_mjy`, joined by a line
  within each detector only (no line across a detector boundary). With `all_visits=True`, one
  colour per `visit`. A channel average with `channel_n` = 1 is a single measurement; the static
  figure draws it like the others, but its error bar is that measurement's own error.
- **Lower limit** (`state` saturated, `flux_min_mjy` finite): an upward triangle at `flux_min_mjy`.
- **Not measured** (`state` masked): an open square at the bottom of the plot, legend
  "masked: not measured".
- **Not used** (`state` flagged): a cross at the bottom of the plot, legend "flagged, not used".

Show `table.meta["warning"]` with either chart (see below).

## Warnings: `table.meta["warning"]`

Set by `light_curve_figure` and `spectrum_figure` (absent when there is nothing to say). Several
can be joined into one text:
- saturated target: the points are lower limits (both functions);
- tolerance above `MAX_SAFE_TOL`: the window mixes wavelengths (light curve);
- usable points more than `WL_SPREAD_UM` apart in wavelength: on a steep spectrum that alone can
  change the flux by several percent (light curve);
- measurements from more than one data release: a step between releases may be calibration, not
  a real change (light curve, and spectrum with `all_visits=True`);
- Gaia stars inside the 12″ measuring circle, with their G magnitude and distance: the
  brightnesses are upper limits. A neighbour within 8″ is named as the main source of the light
  at wavelengths where the target is faint (both functions; skipped silently if Gaia cannot be
  reached).

## Progress

The slow functions (`player_html`, `flipbook`, `picture`, `epochs`, `overlay_figure`,
`light_curve_figure`, `spectrum_figure`) take `progress=None`: an optional callable
`progress(stage, done, total)` that is told how far the work has got, so the app can show a
progress bar while a new target downloads.

- `stage` is short plain text, one of `spherex.progress.STAGES`: `"searching the archive"`,
  `"downloading images"`, `"cleaning and aligning"`, `"stacking visits"`, `"measuring"`,
  `"drawing"`.
- It is called with `done=0` when a stage starts and again after each item (`done` = items
  finished, `total` = items in the stage). Cached images count as items too, so a cached target
  runs through the same stages in seconds.
- Stages that have nothing to do are skipped: a frame list already in `cache/frames` is not
  searched, and stacks already in memory report nothing at all (the call returns at once).
- Order: video and pictures: searching (new targets), downloading images, cleaning and aligning,
  stacking visits, drawing. `picture(kind="banddiff" | "rgb")` runs the stacking stages once per
  detector. Overlays: the stacking stages, then searching the archive once per catalogue, then
  drawing. Light curve and spectrum: searching (new targets), downloading images, measuring,
  searching the archive (Gaia neighbours), drawing. `spectrum_figure(all_visits=True)`
  downloads every visit's images in one pass and counts "measuring" over all of them.
- The callback runs in the caller's thread, between items. Anything it raises is caught and
  ignored, and results are identical with and without it.
- The lower-level functions take the same argument: `make_epochs`, `stack_epoch`, `prefetch`,
  `download.get_cutouts`, `light_curve`, `spectrum`, `frames.find_frames`.

```python
def progress(stage, done, total):
    print(f"{stage}: {done} / {total}")

html = api.player_html("WISE 0855", detector="D6", progress=progress)
```

`spherex.progress.Estimate` turns those calls into a line for a progress bar with the time left:
the average time per item so far in the current stage times the items left, shown once at least
2 items of the stage are done. For downloads it also counts retries and "busy" (HTTP 503)
replies since the stage began. `update()` returns a dict with `stage`, `count` ("23 / 61"),
`fraction` (0..1, for `st.progress`), `seconds_left`, `time_left`, `retries`, `busy` and `text`:

```python
from spherex.progress import Estimate

est = Estimate()
def progress(stage, done, total):
    info = est.update(stage, done, total)
    bar.progress(info["fraction"])
    line.caption(info["text"])   # downloading images · 23 / 61 · about 2 min left · 3 retries (2 busy)
```

Cached images make the early items of "downloading images" fast, so the first estimate of a
partly cached target is too short and grows as real downloads begin.

## Errors

Bad input and missing data raise `ValueError` with a message written for users (unknown name,
unknown detector, field of view out of range, no images, not in the offline cache in demo mode,
the same visit twice in a pair, more than 150 pictures with `days=0`, fewer than 2 chosen pictures
for a difference video). A failed server call raises `OSError`: in demo mode after one
short try (for example a target whose frame list is not in `cache/`), otherwise after retries.
Catch both: `except ValueError as e: st.warning(str(e))`, then `except Exception` for anything else.

## Speed (measured on the cached test targets)

| Situation | Time |
|---|---|
| First video of a cached target (stacking the visits) | 2-7 s |
| Same target and settings again, other video modes | 0.2-0.4 s (memory cache) |
| GIF | about 1 s (every frame: 15-20 s) |
| Player, every frame (`days=0`) | 4-6 s, about 2 MB |
| Deep or pair picture after the video | 0.1 s |
| Band difference, RGB | 1-6 s |
| Overlay (catalogues cached) | 0.2-0.3 s |
| Light curve | 3-6 s |
| Spectrum, latest visit / every visit | 5-8 s / 9-23 s |
| New target, or images not in `cache/` (demo mode off) | minutes (downloads from IRSA, 6-12 at a time, fewer when the archive is busy) |

`clip=False` builds a separate set of stacks (same time again the first time).

## Deployment

- Ship the `cache/` folder (frames, cutouts, gaia, wise) with the app: the five test targets then
  work without downloads.
- `python tools/prepare_demo.py` fills it for the test targets; `api.visits(text, refresh=True)` picks up
  new SPHEREx releases.
- URL parameters: `app_example.py` reads and writes `?target=WISE+0855&detector=D6&fov=6&view=video&mode=normal`.
