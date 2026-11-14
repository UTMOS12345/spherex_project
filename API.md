# spherex.api: guide for the web app

The app only needs `from spherex import api, set_style`. `cache/` is found next to the
`spherex/` package wherever Python starts (`SPHEREX_CACHE=/path` overrides it). A working example
is `app_example.py` (`streamlit run app_example.py`).

## For the app

- **Turn demo mode on at start** for a live demo: `api.set_demo_mode(True)` (or start with
  `SPHEREX_DEMO=1`). Without it, any setting whose images are not in `cache/` downloads them from
  IRSA, which takes minutes, and on a bad network each image is retried for minutes more.
- **Show `table.meta["warning"]` on the page** (`st.warning(...)`) whenever a returned table has
  it. It explains saturation, neighbouring stars in the measuring circle, mixed data releases and
  wide wavelength windows. The same text is drawn small at the bottom of the figure; that is not
  enough on its own.
- **Use `api.defaults(text)`** for the per-target detector, light-curve wavelength and tolerance.
  For the five test targets these are the settings already in `cache/`, and the function also
  recognises aliases and coordinates of those targets.

## Settings

| Name | What it is |
|---|---|
| `api.set_demo_mode(on)` | `True`: no downloads; frames not in `cache/` are skipped; every server call gets one try with a 20 s deadline. Also set by the environment variable `SPHEREX_DEMO=1`. |
| `api.demo_mode()` | `True` when demo mode is on. |
| `api.defaults(text)` | dict `detector`, `band` (µm), `tol` (µm) for a target: the cached settings for the five test targets (`api.DEMO_DEFAULTS`), else `api.OTHER_DEFAULTS` (D2, 1.6, 0.02). |
| `api.MAX_FOV` | 10.0: the largest field of view in arcmin. |
| `api.MAX_SAFE_TOL` | 0.05: light curves with a wider wavelength window get a warning. |
| `set_style(dark=False)` | from `spherex`: one look for every figure; call once, `dark=True` for a dark page. |

## Functions

| Feature | Call | Returns |
|---|---|---|
| Search box | `api.resolve(text)` | dict: `name`, `ra`, `dec` (degrees, catalogue position), `ra_hms`, `dec_dms`, `has_motion`, `pm_ra`, `pm_dec` (mas/yr), `known` (True for the five test targets) |
| Visits | `api.visits(text, refresh=False)` | table: `visit`, `first_date`, `last_date`, `n_frames`, `D1`..`D6` (frames per detector), `releases` |
| Video (GIF) | `api.flipbook(text, detector="D2", fov=4.0, mode="normal", fps=3, wl=None, days=60, timeline=True)` | GIF bytes |
| Video (player) | `api.player_html(text, detector="D2", fov=4.0, mode="normal", fps=3, wl=None, days=60, width=700)` | HTML string: the same pictures with play/pause, step and a slider (`streamlit.components.v1.html(html, height=...)`) |
| Pictures | `api.picture(text, kind="visit", detector="D2", fov=4.0, visit=-1, a=-1, b=0, wl=None, long="D6", short="D2", rgb="D6,D3,D1")` | figure |
| Overlays | `api.overlay_figure(text, detector="D2", fov=4.0, visit=-1, gaia=True, wise=True, asteroids=False, min_pm=50, arrow_years=5)` | (figure, notes dict) |
| Light curve | `api.light_curve_figure(text, band=1.6, tol=0.02)` | (figure, table) |
| Spectrum | `api.spectrum_figure(text, visit=-1, all_visits=False)` | (figure, table) |
| Flags | `api.flags_figure(text, detector="D2", visit=-1, frame=0)` | (figure, table) |

Show a figure with `st.pyplot(fig)` and then `plt.close(fig)`; a table with
`st.dataframe(table.to_pandas())`; GIF bytes with `st.image(gif)`.

## Inputs

- `text`: a name ("WISE 0855"), degrees ("133.795 -7.245"), or sexagesimal
  ("08h55m10.8s -07d14m42.5s", "08:55:10.8 -07:14:42.5", "08 55 10.8 -07 14 42.5"). The two parts
  may be separated by a comma and labelled: "RA 08h55m10.831s, Dec -7d14m42.53s", "RA=133.79 Dec=-7.24".
  Coordinates within 10″ of a test target's catalogue, Gaia DR3 (2016.0) or present-day position
  are treated as that target, with its proper motion.
- `detector`: "D1".."D6", a combination "D5+D6" (also "5+6", "D5,D6"), or "all".
- `wl`: a wavelength range in micron, "4.4-4.7", between 0.75 and 5.0. With `wl`, `detector` may
  be `None` (the detectors covering the range are used).
- `fov`: picture width in arcmin, 1 to 10.
- `mode` (`flipbook`, `player_html`): "normal" (one picture per visit), "difference" (each visit
  minus the first), "minusmean" (each visit minus the average of the others).
- `days`: the longest time one picture may cover: 60 = one picture per visit; 7 = weekly pictures
  (more pictures, each noisier).
- `timeline` (`flipbook`): a time bar under the picture, and each picture stays on screen longer
  when the gap to the next is longer.
- `kind` (`picture`): "visit" (visit number `visit`), "deep" (all visits added), "pair" (visit
  `a` minus visit `b`; red = brighter in `a`), "banddiff" (`long` minus scaled `short`, latest
  visit with both), "rgb" (`rgb` = "red,green,blue" detectors, latest visit with all three).
- Visit numbers: 0 = first, -1 = latest.
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
motions were ignored), `asteroids_in_view` (when asked for), and `verdict`, present when both Gaia
and WISE were drawn. `verdict` is a catalogue check, not a detection, and says so.

`light_curve_figure` table: `mjd`, `date`, `wavelength_um`, `flux_mjy`, `err_mjy`,
`flux_min_mjy`, `detector`, `n_bad`, `saturated`, `bad_flags`, `ok`, `release` ("DR1", "QR3", ...).
`flux_mjy` is NaN where the star is saturated; `flux_min_mjy` is then a lower limit. Only rows with
`ok` True are used for the visit averages. Each release has its own marker on the figure.

`spectrum_figure` table: one row per channel with data: `detector`, `channel` (1-17),
`wavelength_um` (channel centre), `flux_mjy` (mean), `err_mjy`, `n`. With `all_visits=True` there
is also a `visit` column. For a saturated target the table is every single measurement instead
(columns `wavelength_um`, `flux_mjy`, `err_mjy`, `flux_min_mjy`, `detector`, `mjd`, `n_bad`,
`saturated`, `bad_flags`, `ok`, and `visit` with `all_visits=True`).

`flags_figure` table: `flag`, `bit`, `percent_of_pixels`, `masked` (whether this tool masks
it), only flags present in that exposure. If the requested exposure is not in `cache/` in demo
mode, the next one of that visit that is cached is shown.

## Warnings: `table.meta["warning"]`

Set by `light_curve_figure` and `spectrum_figure` (absent when there is nothing to say). Several
can be joined into one text:
- saturated target: the points are lower limits (both functions);
- tolerance above `MAX_SAFE_TOL`: the window mixes wavelengths (light curve);
- measurements from more than one data release: a step between releases may be calibration, not
  a real change (light curve only);
- Gaia stars inside the 12″ measuring circle, with their G magnitude and distance: the
  brightnesses are upper limits (both functions; skipped silently if Gaia cannot be reached).

## Errors

Bad input and missing data raise `ValueError` with a message written for users (unknown name,
unknown detector, field of view out of range, no images, not in the offline cache in demo mode).
Network failures outside demo mode raise `OSError` after retries. Catch both:
`except ValueError as e: st.warning(str(e))`, then `except Exception` for anything else.

## Speed (measured on the cached test targets)

| Situation | Time |
|---|---|
| First video of a cached target (stacking the visits) | 3-7 s |
| Same target and settings again, other video modes | 0.2-0.4 s (memory cache) |
| GIF | about 1 s |
| Deep or pair picture after the video | 0.1 s |
| Band difference, RGB | 1-6 s |
| Overlay (catalogues cached) | 0.2-0.3 s |
| Light curve | 3-6 s |
| Spectrum, latest visit / every visit | 5-8 s / 9-23 s |
| New target, or images not in `cache/` (demo mode off) | minutes (downloads from IRSA, one at a time) |

## Deployment

- Ship the `cache/` folder (frames, cutouts, gaia, wise) with the app: the five test targets then
  work without downloads.
- `python prepare_demo.py` fills it for the test targets; `api.visits(text, refresh=True)` picks up
  new SPHEREx releases.
- URL parameters: `app_example.py` reads and writes `?target=WISE+0855&detector=D6&fov=6&view=video&mode=normal`.
