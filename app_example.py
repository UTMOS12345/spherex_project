"""SPHEREx Flipbook - minimal Streamlit interface on top of spherex.api.

    pip install streamlit
    streamlit run app_example.py

Link to a view:  ?target=WISE+0855&detector=D6&fov=6&view=video&mode=normal
"""
import matplotlib.pyplot as plt
import streamlit as st
import streamlit.components.v1 as components

from spherex import api, set_style

# Detector and wavelength that suit each test target (and that prepare_demo.py caches).
EXAMPLES = {
    "Barnard's Star": ("D2", 1.3),
    "Epsilon Indi B": ("D5", 4.2),
    "WISE 0855": ("D6", 4.5),
    "RW Aur": ("D1", 0.9),
    "R Draconis": ("D3", 2.2),
}
VIEWS = ["video", "compare", "overlays", "light curve", "spectrum", "data"]
MODES = ["normal", "difference", "minusmean"]

st.set_page_config(page_title="SPHEREx Flipbook", layout="centered")
set_style(dark=True)
st.markdown("""
<style>
  #MainMenu, footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] {display: none;}
  .block-container {max-width: 760px; padding-top: 2.2rem;}
  h1 {font-size: 1.05rem; font-weight: 600; letter-spacing: .02em; margin: 0 0 1.2rem 0;}
  .stButton button, .stDownloadButton button {border-radius: 2px; border: 1px solid #383835;
      background: transparent; font-size: .85rem; padding: .25rem .7rem;}
  .stButton button:hover {border-color: #c3c2b7; color: #f0efec;}
  .stTextInput input, .stNumberInput input {border-radius: 2px;}
  .meta {color: #c3c2b7; font-size: .85rem; margin: -.4rem 0 1rem 0;}
  hr {margin: 1rem 0; border-color: #2a2a28;}
</style>
""", unsafe_allow_html=True)

q = st.query_params
if "target" not in st.session_state:
    st.session_state.target = q.get("target", "Epsilon Indi B")
    st.session_state.detector = q.get("detector", EXAMPLES.get(st.session_state.target, ("D2", 1.6))[0])
    st.session_state.wl = q.get("wl", "")
    try:
        st.session_state.fov = min(10.0, max(2.0, float(q.get("fov", 4.0))))
    except ValueError:
        st.session_state.fov = 4.0
    st.session_state.view = q.get("view") if q.get("view") in VIEWS else "video"
    st.session_state.mode = q.get("mode") if q.get("mode") in MODES else "normal"


def pick(name):
    st.session_state.target = name
    st.session_state.detector = EXAMPLES[name][0]


def show(fig):
    st.pyplot(fig)
    plt.close(fig)


@st.cache_data(show_spinner=False)
def player(text, detector, fov, mode, wl):
    return api.player_html(text, detector or None, fov, mode, 3, wl or None, width=700)


@st.cache_data(show_spinner=False)
def gif(text, detector, fov, mode, wl):
    return api.flipbook(text, detector or None, fov, mode, 3, wl or None)


# ---------------- input ----------------
st.title("SPHEREx Flipbook")
text = st.text_input("target", key="target", label_visibility="collapsed",
                     placeholder="name or coordinates, e.g. 08h55m10.8s -07d14m42.5s")
for col, name in zip(st.columns(len(EXAMPLES)), EXAMPLES):
    col.button(name, on_click=pick, args=(name,), use_container_width=True)

with st.expander("options"):
    c1, c2, c3 = st.columns(3)
    detector = c1.text_input("detector", key="detector", help="D1 to D6, a sum like D5+D6, or all")
    wl = c2.text_input("wavelength range, µm", key="wl", help="for example 4.4-4.7; overrides the detector")
    fov = c3.slider("field of view, arcmin", 2.0, 10.0, step=0.5, key="fov")

view = st.radio("view", VIEWS, horizontal=True, label_visibility="collapsed", key="view")
st.divider()
band_default = EXAMPLES.get(text, (None, 1.6))[1]

# ---------------- output: only the chosen view runs ----------------
try:
    info = api.resolve(text)
    motion = f" · moves {(info['pm_ra'] ** 2 + info['pm_dec'] ** 2) ** .5 / 1000:.1f}″ per year" if info["has_motion"] else ""
    st.markdown(f"<div class='meta'>{info['ra_hms']} {info['dec_dms']}{motion}</div>", unsafe_allow_html=True)
    if "mode" not in st.session_state:       # Streamlit forgets a widget's value while it is hidden
        st.session_state.mode = st.session_state.get("mode_keep", "normal")
    mode = st.session_state.mode

    if view == "video":
        mode = st.radio("mode", MODES, horizontal=True, label_visibility="collapsed", key="mode")
        st.session_state.mode_keep = mode
        with st.spinner("building the video"):
            html = player(text, detector, fov, mode, wl)
            components.html(html, height=800)           # an HTML page, not a URL: st.iframe would not render it
        st.caption("The circle marks where the target should be on each date. "
                   "difference: each visit minus the first. minusmean: each visit minus the others.")
        if st.button("make a GIF"):
            st.download_button("download", gif(text, detector, fov, mode, wl),
                               file_name="spherex_flipbook.gif", mime="image/gif")

    elif view == "compare":
        kind = st.radio("picture", ["deep", "pair", "banddiff", "rgb"], horizontal=True,
                        label_visibility="collapsed")
        st.caption({"deep": "All visits added.",
                    "pair": "Latest visit minus the first. Red: brighter now. Blue: brighter then.",
                    "banddiff": "D6 minus scaled D2. Ordinary stars cancel; cold objects stay red. Needs both detectors.",
                    "rgb": "D6, D3, D1 as red, green, blue. Needs all three detectors."}[kind])
        if kind in ("deep", "pair") or st.button("make picture"):
            with st.spinner("making the picture"):
                show(api.picture(text, kind, detector=detector or "D2", fov=fov, wl=wl or None))

    elif view == "overlays":
        c1, c2, c3 = st.columns(3)
        g, w, a = c1.checkbox("Gaia DR3", True), c2.checkbox("WISE", True), c3.checkbox("asteroids")
        with st.spinner("reading catalogues"):
            fig, notes = api.overlay_figure(text, detector or "D2", fov, gaia=g, wise=w, asteroids=a)
        show(fig)
        if "verdict" in notes:
            st.caption(notes["verdict"])
        for f in notes["failed"]:
            st.caption(f"not available: {f}")

    elif view == "light curve":
        c1, c2 = st.columns(2)
        band = c1.number_input("wavelength, µm", 0.75, 5.0, float(band_default), 0.1)
        tol = c2.number_input("tolerance, µm", 0.01, 0.5, 0.02, 0.01)
        if st.button("measure"):
            with st.spinner("measuring"):
                fig, table = api.light_curve_figure(text, band, tol)
            show(fig)
            df = table.to_pandas()
            st.dataframe(df, hide_index=True)
            st.download_button("download CSV", df.to_csv(index=False), file_name="light_curve.csv")

    elif view == "spectrum":
        every = st.checkbox("every visit")
        if st.button("measure"):
            with st.spinner("measuring all channels"):
                fig, table = api.spectrum_figure(text, all_visits=every)
            show(fig)
            df = table.to_pandas()
            st.dataframe(df, hide_index=True)
            st.download_button("download CSV", df.to_csv(index=False), file_name="spectrum.csv")

    elif view == "data":
        st.dataframe(api.visits(text).to_pandas(), hide_index=True)
        with st.spinner("loading one exposure"):
            fig, table = api.flags_figure(text, (detector or "D2").split("+")[0])
        show(fig)
        st.caption("Left: as observed. Right: cleaned; red pixels are masked.")
        st.dataframe(table.to_pandas(), hide_index=True)
        if st.button("check for new data"):
            st.dataframe(api.visits(text, refresh=True).to_pandas(), hide_index=True)

    st.query_params.update(target=text, detector=detector, fov=str(fov), wl=wl, view=view, mode=mode)
except ValueError as e:                      # messages written for users
    st.warning(str(e))
except Exception as e:                       # network and anything unexpected: no traceback on the page
    st.warning(f"That did not work ({type(e).__name__}: {str(e)[:200]}). The archive may be "
               "unreachable; try one of the example targets.")
