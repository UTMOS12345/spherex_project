r"""SPHEREx Flipbook: the Streamlit frontend for the spherex data library.

Built so far: page skeleton, target search with its options, the video view (interactive
player + gif export), the overlays view and the spectrum view.

    $env:SPHEREX_DEMO="1"; .venv\Scripts\python.exe -m streamlit run app.py

Demo mode is on unless the URL has ?live=1. Every API call goes through one lock, and
only the view the user chose is built on a rerun.
"""
import re
import threading

import matplotlib.pyplot as plt
import streamlit as st

from spherex import api, set_style

TARGETS = ["Barnard's Star", "Epsilon Indi B", "WISE 0855", "RW Aur", "R Draconis"]
VIEWS = ["video", "compare", "overlays", "light curve", "spectrum", "data", "about"]
MODES = ["normal", "difference", "minusmean"]
STEPS = list(api.TIME_STEPS)                # "per visit", "monthly", "weekly", "every frame"
# only to fill in the boxes when api.defaults itself fails (it is not an API call)
FALLBACK = dict(detector="D2", band=1.6, tol=0.02)

# Matplotlib figures and the FITS files behind them are not safe with several visitors at
# once, so every api call runs under this one lock.
LOCK = threading.Lock()

st.set_page_config(page_title="SPHEREx Flipbook", layout="centered")
set_style(dark=True)                        # one look for every figure the api returns
st.markdown(
    """
    <style>
    [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer {visibility: hidden;}
    .block-container {max-width: 760px; padding-top: 1.5rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

q = st.query_params
LIVE = q.get("live") == "1"
api.set_demo_mode(not LIVE)                 # before the first API call, always


# ------------------------------------------------------------------ helpers
def call(fn, *args, **kwargs):
    """Every api call goes through here: one lock for the whole app."""
    with LOCK:
        return fn(*args, **kwargs)


def guarded(panel):
    """Build one panel. The api writes its ValueError messages for users, so show those as
    they are; anything else becomes one short sentence. True if the panel worked."""
    try:
        panel()
        return True
    except ValueError as e:
        msg = str(e)
        # api._epochs uses this wording when demo mode has no cached images for the request
        if api.demo_mode() and "offline cache" in msg:
            st.warning(msg)
        else:
            st.error(msg)
    except Exception:
        st.error("This part could not be made. The data may not be downloaded yet; "
                 "try again or pick another setting.")
    return False


def show(fig):
    st.pyplot(fig)
    plt.close(fig)                          # free the figure; matplotlib keeps every one open


def embed_html(html, height):
    """One self-contained HTML page in an iframe. Streamlit 1.67 renamed
    components.html to st.iframe; older installs only have the first."""
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        import streamlit.components.v1 as components
        components.html(html, height=height, scrolling=False)


@st.cache_data(show_spinner=False, max_entries=24)
def cached_defaults(text, live):
    """detector/band/tolerance for a target. `live` is only part of the cache key: with
    ?live=1 a name lookup may reach the network, so the two modes must not share a result."""
    return call(api.defaults, text)


@st.cache_data(show_spinner=False, max_entries=12)
def cached_player(text, detector, fov, mode, wl, fps, live, clip, days):
    """The interactive player as one HTML page. `live` is only part of the cache key: live mode
    may see other data. clip=False and each time step (days) are different sets of pictures."""
    return call(api.player_html, text, detector, fov, mode, fps, wl, days, width=600, clip=clip)


@st.cache_data(show_spinner=False, max_entries=8)
def cached_flipbook(text, detector, fov, mode, wl, fps, live, clip, days):
    """GIF bytes for the export button. Same key rule as the player."""
    return call(api.flipbook, text, detector, fov, mode, fps, wl, days, clip=clip)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_epochs(text, detector, fov, wl, clip, days, live):
    """One row per picture of the player with these settings (api.epochs). It shares the stacks
    the player builds, so after the player it is one cheap call."""
    return call(api.epochs, text, detector, fov, wl, days, clip)


@st.cache_data(show_spinner=False, max_entries=8)
def cached_visits(text, live):
    """One row per SPHEREx visit, for the spectrum's visit picker. Without a detector this
    only reads the cached frame tables, so it does not stack images."""
    return call(api.visits, text)


def url_fov():
    """Field of view from the URL, clamped to the slider (a bad value falls back to 4')."""
    try:
        v = float(q.get("fov", 4.0))
    except (TypeError, ValueError):
        return 4.0
    return min(max(v, 2.0), float(api.MAX_FOV))


def url_days():
    """Time step from the URL: one of the api.TIME_STEPS values, else one picture per visit."""
    try:
        v = int(q.get("days", 60))
    except (TypeError, ValueError):
        return 60
    return v if v in api.TIME_STEPS.values() else 60


def step_label(days):
    """api.TIME_STEPS value -> its label for the time-step box."""
    return next((k for k, v in api.TIME_STEPS.items() if v == days), STEPS[0])


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "target"


def target_detector():
    """The detector box, or the target's cached default when the box is empty (a wavelength
    range on its own is fine for the video, but the overlays need one detector)."""
    det = st.session_state["detector"].strip()
    if det:
        return det
    try:
        return cached_defaults(st.session_state["target"], LIVE)["detector"]
    except Exception:
        return FALLBACK["detector"]


def picture_counts(text, detector, fov, wl, clip, days):
    """api.epochs meta for these settings: n_pictures, n_frames_total, n_few_frames (pictures
    resting on fewer than 4 frames under the centre), or None. api.epochs shares the stacks the
    player already built, so this is one cheap call. A failure here drops the line, never the video."""
    try:
        return dict(cached_epochs(text, detector, fov, wl, clip, days, LIVE).meta)
    except Exception:
        return None


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


EVERY_FRAME_NOTE = ("single exposures: brightness flickers because each frame sees a slightly "
                    "different wavelength; fast movers such as asteroids show here and not in "
                    "stacked pictures.")


# ------------------------------------------------------------------ state
def first_setup():
    """Fill st.session_state once, starting from the URL."""
    if "target" in st.session_state:
        return
    st.session_state["target"] = (q.get("target", "Barnard's Star") or "").strip() or "Barnard's Star"
    sug = FALLBACK
    try:                                    # api.defaults returns OTHER_DEFAULTS for unknown input
        sug = cached_defaults(st.session_state["target"], LIVE)
    except Exception:
        pass
    st.session_state["detector"] = q.get("detector", sug["detector"])
    st.session_state["wl"] = q.get("wl", "")
    st.session_state["band"] = float(sug["band"])
    st.session_state["tol"] = float(sug["tol"])
    st.session_state["fov"] = url_fov()
    st.session_state["view"] = q.get("view") if q.get("view") in VIEWS else "video"
    st.session_state["mode"] = q.get("mode") if q.get("mode") in MODES else "normal"
    st.session_state["raw"] = q.get("clip") == "0"      # ?clip=0 -> plain average of the frames
    st.session_state["days"] = url_days()               # time step; not a widget key, so it survives view changes
    st.session_state["_defaults_for"] = st.session_state["target"]


def pick_target(name):
    """A test-target button was pressed: use the detector and wavelength cached for it."""
    st.session_state["target"] = name
    st.session_state["_defaults_for"] = None


def refresh_defaults():
    """Target changed (typed or a button): put that target's cached settings back."""
    target = st.session_state["target"]
    if st.session_state.get("_defaults_for") == target:
        return
    try:
        sug = cached_defaults(target, LIVE)
    except Exception:
        sug = FALLBACK
    st.session_state["detector"] = sug["detector"]
    st.session_state["wl"] = ""
    st.session_state["band"] = float(sug["band"])
    st.session_state["tol"] = float(sug["tol"])
    st.session_state["_defaults_for"] = target


# ------------------------------------------------------------------ panels
def header():
    """One line: name, coordinates, proper motion if the catalogue knows it."""
    info = call(api.resolve, st.session_state["target"])
    line = f"**{info['name']}** &nbsp;·&nbsp; {info['ra_hms']} {info['dec_dms']}"
    if info["has_motion"]:
        line += (f" &nbsp;·&nbsp; proper motion {info['pm_ra']:.0f}, {info['pm_dec']:.0f} mas/yr"
                 " (RA, Dec)")
    st.markdown(line)


READ_PLAYER = {
    "normal": "each picture is one visit; the green circle is where the target should be. "
              "use play, the arrows or the slider to step through the visits.",
    "difference": "each picture is a visit minus the first: red = brighter than the first "
                  "visit, blue = fainter; a star that moves leaves a red spot and a blue spot.",
    "minusmean": "each picture is a visit minus the average of the other visits: red = "
                 "brighter than usual, blue = fainter.",
}


def video_panel():
    mode = st.radio("mode", MODES, horizontal=True, key="mode")
    c1, c2 = st.columns([3, 2])
    fps = c1.slider("pictures per second", 1, 8, 3, key="fps")
    step = c2.selectbox("time step", STEPS, index=STEPS.index(step_label(st.session_state["days"])),
                        key="step", help="How long one picture may cover: one per visit, per month, "
                                         "per week, or every single frame.")
    st.session_state["days"] = api.TIME_STEPS[step]
    text = st.session_state["target"].strip()
    detector = st.session_state["detector"].strip() or None
    wl = st.session_state["wl"].strip() or None
    fov = float(st.session_state["fov"])
    clip = not st.session_state["raw"]
    days = st.session_state["days"]
    key = (text, detector, fov, mode, wl, fps, LIVE, clip, days)

    with st.spinner("building the player..."):
        html = cached_player(*key)
    # 800 px leaves room for a square picture plus the control bar, so nothing needs scrolling
    embed_html(html, height=800)
    counts = picture_counts(text, detector, fov, wl, clip, days)
    if counts:
        line = (f"{plural(counts['n_pictures'], 'picture')} from "
                f"{plural(counts['n_frames_total'], 'frame')}")
        if counts["n_few_frames"]:
            line += f", {counts['n_few_frames']} built from few frames"
        st.caption(line + (". " + EVERY_FRAME_NOTE if days == 0 else ""))
        if counts["n_few_frames"] and days != 0:     # every frame: all of them, said above
            st.warning(f"{api.FEW_FRAMES_NOTE}: some pictures here rest on fewer than 4 frames "
                       "under the centre, so one bad frame can survive in them.")
    st.caption(READ_PLAYER[mode])

    # the gif is only built when asked for; its bytes stay for as long as the settings do
    if st.button("export gif", key="export_gif"):
        with st.spinner("building the gif..."):
            st.session_state["gif"] = (key, cached_flipbook(*key))
    gif = st.session_state.get("gif")
    if gif and gif[0] == key:
        st.download_button("download gif", gif[1], mime="image/gif",
                           file_name=f"spherex_{slug(text)}_{mode}.gif")


def overlay_caption(gaia, wise, asteroids):
    """The grey how-to-read line lists only what this picture actually draws."""
    parts = []
    if gaia:
        parts.append("circles = Gaia DR3")
    if wise:
        parts.append("squares = WISE (pink = slow, orange = fast)")
    if asteroids:
        parts.append("diamonds = known asteroids")
    if gaia or wise:
        parts.append("arrows = motion over the next 5 years")
    parts.append("green = the target's predicted position")
    return "; ".join(parts) + "."


def overlays_panel():
    c1, c2, c3 = st.columns(3)
    gaia = c1.checkbox("gaia dr3", True, key="ov_gaia")
    wise = c2.checkbox("wise", True, key="ov_wise")
    asteroids = c3.checkbox("asteroids", False, key="ov_asteroids")
    if asteroids and not LIVE:
        # the asteroid lookup is a network query, so demo mode must not wait for it
        st.caption("asteroid positions need the network, so they are not drawn in demo mode.")
    with st.spinner("querying catalogues..."):
        fig, notes = call(api.overlay_figure, st.session_state["target"], target_detector(),
                          float(st.session_state["fov"]), gaia=gaia, wise=wise,
                          asteroids=asteroids and LIVE)
    show(fig)
    if notes.get("few_frames"):         # the title says it too, but small and easy to miss
        st.warning(f"{api.FEW_FRAMES_NOTE}: this picture rests on fewer than 4 frames under "
                   "the centre, so one bad frame can survive in it.")
    st.caption(overlay_caption(gaia, wise, asteroids and LIVE))
    if "verdict" in notes:             # only when both catalogues were asked for
        st.info(notes["verdict"])
    for failed in notes["failed"]:     # one warning per catalogue that could not be reached
        st.warning(f"overlay not available: {failed}")
    if notes.get("wise_halo_stars"):
        st.caption(f"{notes['wise_halo_stars']} bright Gaia star(s) near the target have no "
                   "WISE counterpart: their halos hide the WISE motions around them.")


SPECTRUM_READ_ONE = ("small dots = single measurements; large dots joined by a line = the average "
                     "in each channel; grey x = flagged; grey triangles = lower limits of a "
                     "saturated star (its true brightness is higher).")
SPECTRUM_READ_ALL = ("one line per visit; a visit drawn only as triangles is saturated, so its "
                     "true brightness is higher; compare the shapes, not single points.")


def spectrum_panel():
    """Brightness at every wavelength for one visit, or for all of them. The visit numbers are
    the rows of api.visits: api.spectrum_figure counts visits in that same order."""
    text = st.session_state["target"].strip()
    every = st.checkbox("every visit", key="spec_every")
    visits = cached_visits(text, LIVE)          # raises the api's readable message if no data
    labels = [f"visit {int(r['visit'])}: {r['first_date']} to {r['last_date']} "
              f"({int(r['n_frames'])} frames)" for r in visits]
    if not labels:
        st.info("no visits with images for this target.")
        return
    idx = st.selectbox("visit", list(range(len(labels))), index=len(labels) - 1,
                       format_func=labels.__getitem__, disabled=every, key="spec_visit")

    if not st.button("measure", key="spec_run"):
        return                                  # the spectrum is only measured on a press
    with st.spinner("measuring the spectrum..."):
        fig, table = call(api.spectrum_figure, text, visit=idx, all_visits=every)
    show(fig)
    warning = table.meta.get("warning")         # saturation, neighbours, mixed releases
    if warning:
        st.warning(warning)
    st.caption(SPECTRUM_READ_ALL if every else SPECTRUM_READ_ONE)
    df = table.to_pandas()
    st.dataframe(df, hide_index=True)
    st.download_button("download csv", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"spectrum_{slug(text)}.csv", mime="text/csv",
                       on_click="ignore")   # keep the figure on the page while the file downloads


# ------------------------------------------------------------------ page
first_setup()
st.title("SPHEREx Flipbook")

st.text_input("target (name or coordinates)", key="target",
              placeholder="Barnard's Star, WISE 0855, 133.795 -7.245")

cols = st.columns(len(TARGETS))
for col, name in zip(cols, TARGETS):
    col.button(name.lower(), key=f"pick_{name}", use_container_width=True,
               on_click=pick_target, args=(name,))

refresh_defaults()                  # before the detector box, so its state is already right

with st.expander("options"):
    st.text_input("detector(s): D1 to D6, D5+D6, or all", key="detector",
                  help="The default is the detector that is already cached for this target.")
    st.text_input("wavelength range in micron, for example 4.4-4.7 (optional)", key="wl")
    st.slider("field of view in arcmin", 2.0, float(api.MAX_FOV), step=0.5, key="fov")
    st.toggle("raw average (clip=False)", key="raw",
              help="Plain average of the frames instead of the clipped mean: keeps fast movers "
                   "and short flares, but also single-frame defects. It does not affect the "
                   "measurements (light curve, spectrum, flags).")

if LIVE:
    st.caption("live mode: new targets and settings may download from IRSA (this can take "
               "minutes).")
else:
    st.caption("demo mode: only images already in cache/ are shown. Add ?live=1 to the URL "
               "to allow downloads.")

if not st.session_state["target"].strip():
    st.warning("enter a target name or coordinates.")
    st.stop()
if not guarded(header):             # unknown target: one message, no view underneath
    st.stop()

view = st.segmented_control("view", VIEWS, key="view", label_visibility="collapsed",
                            selection_mode="single") or "video"

if view == "video":
    guarded(video_panel)
elif view == "overlays":
    guarded(overlays_panel)
elif view == "spectrum":
    guarded(spectrum_panel)
else:
    st.info(f"the {view} view is built in the next step.")

# keep the link shareable; ?live=1 is left alone because it is not ours
st.query_params.update(
    target=st.session_state["target"],
    detector=st.session_state["detector"],
    fov=f"{float(st.session_state['fov']):.1f}",
    wl=st.session_state["wl"],
    view=view,
    mode=st.session_state.get("mode", "normal"),
    clip="0" if st.session_state["raw"] else "1",
    days=str(st.session_state.get("days", 60)),
)
