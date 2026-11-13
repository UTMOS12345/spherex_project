"""Minimal Streamlit app on top of spherex.api - a starting point for the real app.

    pip install streamlit
    streamlit run app_example.py

Link to a target directly:  http://localhost:8501/?target=WISE+0855&detector=D5%2BD6&fov=6
"""
import matplotlib.pyplot as plt
import streamlit as st

from spherex import api, set_style

st.set_page_config(page_title="SPHEREx Flipbook", layout="wide")
set_style(dark=True)
q = st.query_params                                   # values from the URL, if any

# ---------------- controls ----------------
with st.sidebar:
    st.title("SPHEREx Flipbook")
    text = st.text_input("Target (name or RA Dec)", q.get("target", "WISE 0855"))
    detector = st.text_input("Detector(s): D1..D6, D5+D6, all", q.get("detector", "D5+D6"))
    wl = st.text_input("or wavelength range in µm (e.g. 4.4-4.7)", q.get("wl", ""))
    fov = st.slider("Field of view (arcmin)", 2.0, 10.0, float(q.get("fov", 4.0)), 0.5)
    mode = st.selectbox("Video", ["normal", "difference", "minusmean"])
    fps = st.slider("Speed (pictures per second)", 1, 8, 3)
    st.caption("First search of a new target downloads images and can take minutes.")
st.query_params.update(target=text, detector=detector, fov=str(fov), wl=wl)   # shareable link


def show(fig):
    st.pyplot(fig)
    plt.close(fig)                                    # free the memory


@st.cache_data(show_spinner=False)
def cached_flipbook(text, detector, fov, mode, fps, wl):
    return api.flipbook(text, detector or None, fov, mode, fps, wl or None)


try:
    info = api.resolve(text)
    st.subheader(f"{info['name']}  ·  {info['ra_hms']} {info['dec_dms']}")
    if info["has_motion"]:
        st.caption(f"proper motion {info['pm_ra']:.0f}, {info['pm_dec']:.0f} mas/yr (RA, Dec)")

    tabs = st.tabs(["Video", "Pictures", "Overlays", "Light curve", "Spectrum", "Flags", "Visits"])
    with tabs[0]:
        with st.spinner("Building the video..."):
            st.image(cached_flipbook(text, detector, fov, mode, fps, wl))
    with tabs[1]:
        kind = st.radio("Picture", ["deep", "pair", "banddiff", "rgb"], horizontal=True,
                        help="deep = all visits added; pair = last minus first visit; "
                             "banddiff = D6 minus D2; rgb = D6, D3, D1 as red, green, blue")
        with st.spinner("Making the picture..."):
            show(api.picture(text, kind, detector=detector or "D2", fov=fov))
    with tabs[2]:
        c1, c2, c3 = st.columns(3)
        gaia, wise, ast = c1.checkbox("Gaia DR3", True), c2.checkbox("WISE", True), c3.checkbox("Asteroids")
        with st.spinner("Querying catalogues..."):
            fig, notes = api.overlay_figure(text, detector or "D2", fov, gaia=gaia, wise=wise, asteroids=ast)
        show(fig)
        if "verdict" in notes:
            st.info(notes["verdict"])
        for f in notes["failed"]:
            st.warning(f"overlay not available: {f}")
    with tabs[3]:
        band = st.number_input("Wavelength (µm)", 0.75, 5.0, 1.6, 0.1)
        tol = st.number_input("Tolerance (µm)", 0.01, 0.5, 0.05, 0.01)
        if st.button("Measure light curve"):
            with st.spinner("Measuring..."):
                fig, table = api.light_curve_figure(text, band, tol)
            show(fig)
            st.dataframe(table.to_pandas())
    with tabs[4]:
        every = st.checkbox("Overlay every visit")
        if st.button("Measure spectrum"):
            with st.spinner("Measuring all 102 channels..."):
                fig, table = api.spectrum_figure(text, all_visits=every)
            show(fig)
            st.dataframe(table.to_pandas())
    with tabs[5]:
        with st.spinner("Loading one exposure..."):
            fig, table = api.flags_figure(text, (detector or "D2").split("+")[0])
        show(fig)
        st.dataframe(table.to_pandas())
    with tabs[6]:
        st.dataframe(api.visits(text).to_pandas())
        if st.button("Check for new SPHEREx data"):
            st.dataframe(api.visits(text, refresh=True).to_pandas())
except ValueError as e:                               # readable messages from the API
    st.error(str(e))
