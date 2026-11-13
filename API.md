# spherex.api: guide for the web app

The app only needs `from spherex import api, set_style`. Run everything from the project
folder so `cache/` is found. A working example is `app_example.py` (`streamlit run app_example.py`).

## Functions

| Feature | Call | Returns | Show with |
|---|---|---|---|
| Search box | `api.resolve(text)` | dict: name, ra, dec, ra_hms, dec_dms, has_motion, pm_ra, pm_dec, known | text |
| Visits | `api.visits(text, refresh=False)` | table: one row per visit, frames per detector, releases | `st.dataframe(t.to_pandas())` |
| Video | `api.flipbook(text, detector, fov, mode, fps, wl, days)` | GIF bytes | `st.image(gif)` |
| Pictures | `api.picture(text, kind, detector, fov, visit, a, b, wl, long, short, rgb)` | figure | `st.pyplot(fig)` |
| Overlays | `api.overlay_figure(text, detector, fov, visit, gaia, wise, asteroids)` | (figure, notes dict) | `st.pyplot`, `st.info(notes["verdict"])` |
| Light curve | `api.light_curve_figure(text, band, tol)` | (figure, table) | `st.pyplot`, `st.dataframe` |
| Spectrum | `api.spectrum_figure(text, visit=-1, all_visits=False)` | (figure, table) | same |
| Flags | `api.flags_figure(text, detector, visit, frame)` | (figure, table) | same |

## Inputs

- `text`: a name ("WISE 0855"), degrees ("133.795 -7.245") or sexagesimal ("08h55m10.8s -07d14m42.5s").
- `detector`: "D1".."D6", a combination "D5+D6", or "all".
- `wl`: a wavelength range in micron, "4.4-4.7". With `wl`, `detector` may be `None`.
- `fov`: picture width in arcmin. Up to 10 is served from the standard downloads.
- `flipbook` `mode`: "normal", "difference" (each visit minus the first), "minusmean" (each visit minus the others).
- `flipbook` `days`: 60 = one picture per visit; 7 = weekly pictures (more, noisier).
- `picture` `kind`: "visit", "deep" (all added), "pair" (visit `a` minus visit `b`), "banddiff" (`long` minus scaled `short`), "rgb" ("D6,D3,D1" = red, green, blue).
- Visit numbers: 0 = first, -1 = latest.

## Errors

Bad input raises `ValueError` with a message written for users. Wrap calls in
`try: ... except ValueError as e: st.error(str(e))`.
In `overlay_figure`, a catalogue that cannot be reached is listed in `notes["failed"]`; the figure still comes back.

## Speed

| Situation | Time |
|---|---|
| Target and settings already used in this session | instant (memory) |
| Target in `cache/`, new detector or field of view | seconds (stacking) |
| New target, or frames not in `cache/` | minutes (downloads from IRSA) |
| Light curve or spectrum of a cached target | seconds to a minute |

- Wrap slow calls in `st.spinner(...)`.
- `@st.cache_data` on the flipbook call avoids rebuilding the GIF on every rerun.
- After `st.pyplot(fig)` call `plt.close(fig)`, or memory grows.
- Call `set_style(dark=True)` once at the top; set Streamlit's theme to dark to match.

## Deployment

- Ship the `cache/` folder (frames, cutouts, gaia, wise) with the app: the five challenge targets then work without downloads.
- `python prepare_demo.py` fills it. `api.visits(text, refresh=True)` picks up new SPHEREx releases.
- Link to a target with URL parameters, as `app_example.py` does: `?target=WISE+0855&detector=D5%2BD6&fov=6`.

## Things to tell users

- Saturated stars (Barnard's Star, sometimes RW Aur) have filled cores in pictures and no brightness measurements: grey crosses, "no usable data".
- A combined-detector or deep picture mixes colours or dates: good for seeing, not for measuring.
- Molecule markers on spectra are approximate band centres.
