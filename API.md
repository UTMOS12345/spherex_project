# spherex.api: guide for the web app

The app only needs `from spherex import api, set_style`. `cache/` is found next to the
`spherex/` package wherever Python starts (`SPHEREX_CACHE=/path` overrides it). A working example
is `app_example.py` (`streamlit run app_example.py`).

## For the app

- **Turn demo mode on at start** for a live demo: `api.set_demo_mode(True)` (or start with
  `SPHEREX_DEMO=1`). Without it, any setting whose images are not in `cache/` downloads them from
  IRSA, which takes minutes, and on a bad network each image is retried for minutes more.
- **Show `table.meta["warning"]` on the page** (`st.warning(...)`) whenever a returned table has
  it. It explains saturation, neighbouring stars in the measuring circle, mixed data releases,
  wavelength differences between light-curve points and wide wavelength windows. The same text is
  drawn small at the bottom of the figure; that is not enough on its own.
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

## Settings

| Name | What it is |
|---|---|
| `api.set_demo_mode(on)` | `True`: no downloads; frames not in `cache/` are skipped; every server call gets one try with a 20 s deadline. Also set by the environment variable `SPHEREX_DEMO=1`. |
| `api.demo_mode()` | `True` when demo mode is on. |
| `api.defaults(text)` | dict `detector`, `band` (µm), `tol` (µm) for a target: the cached settings for the five test targets (`api.DEMO_DEFAULTS`), else `api.OTHER_DEFAULTS` (D2, 1.6, 0.02). |
| `api.MAX_FOV` | 10.0: the largest field of view in arcmin. |
| `api.MAX_SAFE_TOL` | 0.05: light curves with a wider wavelength window get a warning. |
| `api.WL_SPREAD_UM` | 0.01: light curves whose usable points differ in wavelength by more than this get a warning. |
| `set_style(dark=False)` | from `spherex`: one look for every figure; call once, `dark=True` for a dark page. |

## Functions

| Feature | Call | Returns |
|---|---|---|
| Search box | `api.resolve(text)` | dict: `name`, `ra`, `dec` (degrees, catalogue position), `ra_hms`, `dec_dms`, `has_motion`, `pm_ra`, `pm_dec` (mas/yr), `known` (True for the five test targets, by name, alias or coordinates) |
| Visits | `api.visits(text, refresh=False, detector=None, fov=4.0, clip=True)` | table: `visit`, `first_date`, `last_date`, `n_frames`, `D1`..`D6` (frames per detector), `releases`; with `detector`, also `n_min` and `clipped_fraction` of that detector's stacks (this stacks the visits if needed) |
| Video (GIF) | `api.flipbook(text, detector="D2", fov=4.0, mode="normal", fps=3, wl=None, days=60, timeline=True, clip=True)` | GIF bytes |
| Video (player) | `api.player_html(text, detector="D2", fov=4.0, mode="normal", fps=3, wl=None, days=60, width=700, clip=True)` | HTML string: the same pictures with play/pause, step and a slider (`streamlit.components.v1.html(html, height=...)`) |
| Pictures | `api.picture(text, kind="visit", detector="D2", fov=4.0, visit=-1, a=-1, b=0, wl=None, long="D6", short="D2", rgb="D6,D3,D1", clip=True)` | figure |
| Overlays | `api.overlay_figure(text, detector="D2", fov=4.0, visit=-1, gaia=True, wise=True, asteroids=False, min_pm=50, arrow_years=5)` | (figure, notes dict) |
| Light curve | `api.light_curve_figure(text, band=1.6, tol=0.02)` | (figure, table) |
| Spectrum | `api.spectrum_figure(text, visit=-1, all_visits=False)` | (figure, table) |
| Flags | `api.flags_figure(text, detector="D2", visit=-1, frame=0)` | (figure, table) |

Show a figure with `st.pyplot(fig)` and then `plt.close(fig)`; a table with
`st.dataframe(table.to_pandas())`; GIF bytes with `st.image(gif)`.

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
- `days`: the longest time one picture may cover: 60 = one picture per visit; 7 = weekly pictures
  (more pictures, each from fewer frames: noisier, and more often "few frames").
- `timeline` (`flipbook`): a time bar under the picture, and each picture stays on screen longer
  when the gap to the next is longer.
- `clip` (`flipbook`, `player_html`, `picture`, `visits`): True = the stacking described above;
  False = plain average of the frames.
- `kind` (`picture`): "visit" (visit number `visit`), "deep" (all visits added), "pair" (the later
  of visits `a` and `b` minus the earlier, whichever order they are given in; red = brighter later,
  blue = brighter earlier), "banddiff" (`long` minus scaled `short`, latest visit with both; red =
  brighter in `long`, blue = brighter in scaled `short`), "rgb" (`rgb` = "red,green,blue"
  detectors, latest visit with all three).
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
motions were ignored), `asteroids_in_view` (when asked for), `n_min`, `few_frames` and
`clipped_fraction` of the visit shown, and `verdict`, present when both Gaia and WISE were drawn.
`verdict` is a catalogue check, not a detection, and says so.

`light_curve_figure` table: `mjd`, `date`, `wavelength_um`, `flux_mjy`, `err_mjy`,
`flux_min_mjy`, `detector`, `n_bad`, `saturated`, `bad_flags`, `ok`, `release` ("DR1", "QR3", ...),
`visit` (the SPHEREx visit the frame belongs to). `flux_mjy` is NaN where the star is saturated
(`flux_min_mjy` is then a lower limit) or where most of the measuring circle is masked (then
`flux_min_mjy` is NaN too: not measured). Only rows with `ok` True go into the visit averages,
one per visit. On the figure each release has its own marker and each point is labelled with
the wavelength it was measured at.

`spectrum_figure` table: one row per channel with data: `detector`, `channel` (1-17),
`wavelength_um` (channel centre), `flux_mjy` (mean), `err_mjy`, `n`. With `all_visits=True` there
is also a `visit` column. For a saturated target the table is every single measurement instead
(columns `wavelength_um`, `flux_mjy`, `err_mjy`, `flux_min_mjy`, `detector`, `mjd`, `n_bad`,
`saturated`, `bad_flags`, `ok`, `release`, and `visit` with `all_visits=True`). On the figure,
grey triangles are lower limits of saturated measurements, open squares "masked: not measured",
crosses "flagged, not used".

`flags_figure` table: `flag`, `bit`, `percent_of_pixels`, `masked` (whether this tool masks
it), only flags present in that exposure. If the requested exposure is not in `cache/` in demo
mode, the next one of that visit that is cached is shown.

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

## Errors

Bad input and missing data raise `ValueError` with a message written for users (unknown name,
unknown detector, field of view out of range, no images, not in the offline cache in demo mode,
the same visit twice in a pair). A failed server call raises `OSError`: in demo mode after one
short try (for example a target whose frame list is not in `cache/`), otherwise after retries.
Catch both: `except ValueError as e: st.warning(str(e))`, then `except Exception` for anything else.

## Speed (measured on the cached test targets)

| Situation | Time |
|---|---|
| First video of a cached target (stacking the visits) | 2-7 s |
| Same target and settings again, other video modes | 0.2-0.4 s (memory cache) |
| GIF | about 1 s |
| Deep or pair picture after the video | 0.1 s |
| Band difference, RGB | 1-6 s |
| Overlay (catalogues cached) | 0.2-0.3 s |
| Light curve | 3-6 s |
| Spectrum, latest visit / every visit | 5-8 s / 9-23 s |
| New target, or images not in `cache/` (demo mode off) | minutes (downloads from IRSA, one at a time) |

`clip=False` builds a separate set of stacks (same time again the first time).

## Deployment

- Ship the `cache/` folder (frames, cutouts, gaia, wise) with the app: the five test targets then
  work without downloads.
- `python prepare_demo.py` fills it for the test targets; `api.visits(text, refresh=True)` picks up
  new SPHEREx releases.
- URL parameters: `app_example.py` reads and writes `?target=WISE+0855&detector=D6&fov=6&view=video&mode=normal`.
