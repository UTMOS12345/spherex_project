r"""SPHEREx Flipbook: the Streamlit frontend for the spherex data library.

Stage 1: page skeleton, target search with its options, and the video view.

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


@st.cache_data(show_spinner=False, max_entries=24)
def cached_defaults(text, live):
    """detector/band/tolerance for a target. `live` is only part of the cache key: with
    ?live=1 a name lookup may reach the network, so the two modes must not share a result."""
    return call(api.defaults, text)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_flipbook(text, detector, fov, mode, wl, fps, live):
    """GIF bytes. Same key rule: a GIF built in live mode is not reused in demo mode."""
    return call(api.flipbook, text, detector, fov, mode, fps, wl)


def url_fov():
    """Field of view from the URL, clamped to the slider (a bad value falls back to 4')."""
    try:
        v = float(q.get("fov", 4.0))
    except (TypeError, ValueError):
        return 4.0
    return min(max(v, 2.0), float(api.MAX_FOV))


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


READ_GIF = {
    "normal": "each picture is one visit; the green circle is where the target should be, "
              "the red dot on the timeline shows which visit is on screen.",
    "difference": "each picture is a visit minus the first: red = brighter than the first "
                  "visit, blue = fainter; a star that moves leaves a red spot and a blue spot.",
    "minusmean": "each picture is a visit minus the average of the other visits: red = "
                 "brighter than usual, blue = fainter.",
}


def video_panel():
    mode = st.radio("mode", MODES, horizontal=True, key="mode")
    fps = st.slider("pictures per second", 1, 8, 3, key="fps")
    text = st.session_state["target"].strip()
    detector = st.session_state["detector"].strip() or None
    wl = st.session_state["wl"].strip() or None
    fov = float(st.session_state["fov"])
    with st.spinner("building the video..."):
        gif = cached_flipbook(text, detector, fov, mode, wl, fps, LIVE)
    st.image(gif)
    st.caption(READ_GIF[mode])
    st.download_button("export gif", gif, mime="image/gif",
                       file_name=f"spherex_{slug(text)}_{mode}.gif")


OVERLAY_READ = ("circles = Gaia DR3, squares = WISE (pink = slow, orange = fast), arrows = "
                "motion over the next 5 years, green = the target's predicted position.")


def overlays_panel():
    c1, c2, c3 = st.columns(3)
    gaia = c1.checkbox("gaia dr3", True, key="ov_gaia")
    wise = c2.checkbox("wise", True, key="ov_wise")
    asteroids = c3.checkbox("asteroids", False, key="ov_asteroids")
    with st.spinner("querying catalogues..."):
        fig, notes = call(api.overlay_figure, st.session_state["target"], target_detector(),
                          float(st.session_state["fov"]), gaia=gaia, wise=wise,
                          asteroids=asteroids)
    show(fig)
    st.caption(OVERLAY_READ)
    if "verdict" in notes:             # only when both catalogues were asked for
        st.info(notes["verdict"])
    for failed in notes["failed"]:     # one warning per catalogue that could not be reached
        st.warning(f"overlay not available: {failed}")
    if notes.get("wise_halo_stars"):
        st.caption(f"{notes['wise_halo_stars']} bright Gaia star(s) near the target have no "
                   "WISE counterpart: their halos hide the WISE motions around them.")


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
)
