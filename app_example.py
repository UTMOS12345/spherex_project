"""Minimal Streamlit app on top of spherex.api - a starting point for the real app.

    pip install streamlit
    streamlit run app_example.py

Link to a target directly:  http://localhost:8501/?target=WISE+0855&detector=D5%2BD6&fov=6

Only the video is made on every page load. Pictures, overlays and flags are made only when
their box is ticked, so a rerun (any click) does not redo slow work the user is not looking at.
"""
import matplotlib.pyplot as plt
import streamlit as st

from spherex import api, set_style

st.set_page_config(page_title="SPHEREx Flipbook", layout="wide")
set_style(dark=True)
q = st.query_params                                   # values from the URL, if any


def url_float(name, default, lo, hi):
    """A number from the URL, clamped to the slider's range (a bad value falls back to default)."""
    try:
        return min(max(float(q.get(name, default)), lo), hi)
    except ValueError:
        return default


# ---------------- controls ----------------
with st.sidebar:
    st.title("SPHEREx Flipbook")
    text = st.text_input("Target (name or RA Dec)", q.get("target", "WISE 0855"))
    suggested = api.defaults(text)                    # the settings already in cache/ for this target
    detector = st.text_input("Detector(s): D1..D6, D5+D6, all", q.get("detector", suggested["detector"]),
                             help=f"{suggested['detector']} is ready offline for this target; "
                                  "other choices may need downloads.")
    wl = st.text_input("or wavelength range in µm (e.g. 4.4-4.7)", q.get("wl", ""))
    fov = st.slider("Field of view (arcmin)", 2.0, api.MAX_FOV, url_float("fov", 4.0, 2.0, api.MAX_FOV), 0.5)
    mode = st.selectbox("Video", ["normal", "difference", "minusmean"])
    fps = st.slider("Speed (pictures per second)", 1, 8, 3)
    demo = st.checkbox("Demo mode: cached data only", value=True,
                       help="No downloads and no long waits: frames not in cache/ are skipped. "
                            "Untick to fetch new targets from IRSA (minutes).")
    api.set_demo_mode(demo)
    st.caption("Demo mode is on: only data already in cache/ is shown." if demo else
               "First search of a new target downloads images and can take minutes.")
st.query_params.update(target=text, detector=detector, fov=str(fov), wl=wl)   # shareable link


def show(fig):
    st.pyplot(fig)
    plt.close(fig)                                    # free the memory


def guarded(fn):
    """Run one panel; a failure shows a message in that panel and the rest of the page still works.
    Returns True if the panel worked."""
    try:
        fn()
        return True
    except ValueError as e:                           # readable messages from the API
        st.error(str(e))
    except Exception as e:                            # network trouble, missing files, bugs
        st.error(f"This part could not be made ({type(e).__name__}: {str(e)[:200]}). "
                 "The data may not be downloaded yet; try again or pick another setting.")
    return False


@st.cache_data(show_spinner=False)
def cached_flipbook(text, detector, fov, mode, fps, wl, demo):     # demo: part of the cache key
    return api.flipbook(text, detector or None, fov, mode, fps, wl or None)


def header():
    info = api.resolve(text)
    st.subheader(f"{info['name']}  ·  {info['ra_hms']} {info['dec_dms']}")
    if info["has_motion"]:
        st.caption(f"proper motion {info['pm_ra']:.0f}, {info['pm_dec']:.0f} mas/yr (RA, Dec); "
                   "position shown is the catalogue position")


def video():
    with st.spinner("Building the video..."):
        st.image(cached_flipbook(text, detector, fov, mode, fps, wl, demo))


def pictures():
    kind = st.radio("Picture", ["deep", "pair", "banddiff", "rgb"], horizontal=True,
                    help="deep = all visits added; pair = last minus first visit; "
                         "banddiff = D6 minus D2; rgb = D6, D3, D1 as red, green, blue "
                         "(banddiff and rgb use other detectors and may need downloads)")
    with st.spinner("Making the picture..."):
        show(api.picture(text, kind, detector=detector or suggested["detector"], fov=fov))


def overlays():
    c1, c2, c3 = st.columns(3)
    gaia, wise, ast = c1.checkbox("Gaia DR3", True), c2.checkbox("WISE", True), c3.checkbox("Asteroids")
    with st.spinner("Querying catalogues..."):
        fig, notes = api.overlay_figure(text, detector or suggested["detector"], fov,
                                        gaia=gaia, wise=wise, asteroids=ast)
    show(fig)
    if "verdict" in notes:
        st.info(notes["verdict"])
    for f in notes["failed"]:
        st.warning(f"overlay not available: {f}")


def light_curve():
    band = st.number_input("Wavelength (µm)", 0.75, 5.0, float(suggested["band"]), 0.1)
    tol = st.number_input("Tolerance (µm)", 0.01, 0.5, float(suggested["tol"]), 0.01)
    if st.button("Measure light curve"):
        with st.spinner("Measuring..."):
            fig, table = api.light_curve_figure(text, band, tol)
        show(fig)
        if "warning" in table.meta:
            st.warning(table.meta["warning"])
        st.dataframe(table.to_pandas())


def spectrum():
    every = st.checkbox("Overlay every visit")
    if st.button("Measure spectrum"):
        with st.spinner("Measuring all 102 channels..."):
            fig, table = api.spectrum_figure(text, all_visits=every)
        show(fig)
        if "warning" in table.meta:
            st.warning(table.meta["warning"])
        st.dataframe(table.to_pandas())


def flags():
    with st.spinner("Loading one exposure..."):
        fig, table = api.flags_figure(text, (detector or suggested["detector"]).split("+")[0])
    show(fig)
    st.dataframe(table.to_pandas())


def visits():
    st.dataframe(api.visits(text).to_pandas())
    if st.button("Check for new SPHEREx data"):
        st.dataframe(api.visits(text, refresh=True).to_pandas())


if not guarded(header):                               # unknown target: one message, not one per tab
    st.stop()
tabs = st.tabs(["Video", "Pictures", "Overlays", "Light curve", "Spectrum", "Flags", "Visits"])
with tabs[0]:
    guarded(video)
for tab, label, panel in [(tabs[1], "Make pictures", pictures), (tabs[2], "Make overlays", overlays),
                          (tabs[5], "Show flags of one exposure", flags)]:
    with tab:
        if st.checkbox(label, key=f"on_{label}"):     # all tabs run on every rerun: only on request
            guarded(panel)
with tabs[3]:
    guarded(light_curve)
with tabs[4]:
    guarded(spectrum)
with tabs[6]:
    guarded(visits)
