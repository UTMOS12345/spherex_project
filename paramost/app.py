r"""SPHEREx Flipbook: the Streamlit frontend for the spherex data library.

Built so far: page skeleton, target search with its options, the video view (interactive
player + gif export), the overlays view, the spectrum view, the light curve view, the about
view, the compare view (deep, pair, band difference, colour) and the data view.

    paramost                          # installed: the launcher starts this file with the theme
    python -m paramost                # from a source checkout, same thing
    SPHEREX_DEMO=1 python -m paramost # a server open to visitors: starts offline

Live is the default: a view that needs images not downloaded yet first says how many and
waits for its Download button. The "Offline" toggle (or SPHEREX_DEMO=1, or ?offline=1 in the
link) uses downloaded data only. Every API call goes through one lock, and only the view the
user chose is built on a rerun.
"""
import contextvars
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

# Started as a script by Streamlit, so the folder above paramost/ (a source checkout) may not be
# on the import path; an installed copy finds spherex anyway and this changes nothing there.
sys.path.insert(1, str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt
import streamlit as st

from spherex import api, set_style, results, workers
from spherex.download import download_workers
from spherex.net import CACHE_ROOT
from spherex.progress import Estimate
from paramost import index as targets_index

REPO_URL = "REPO_URL"                       # placeholder: replace with the repository link
VIEWS = ["video", "compare", "overlays", "light curve", "spectrum", "data", "about"]
MODES = ["normal", "difference", "minusmean"]
STEPS = list(api.TIME_STEPS)                # "per visit", "monthly", "weekly", "every frame"
MAX_PICK = 40                               # more pictures than this: no "choose pictures" box

# Matplotlib figures and the FITS files behind them are not safe with several visitors at
# once, so every api call runs under this one lock.
LOCK = threading.Lock()

st.set_page_config(page_title="SPHEREx Flipbook", layout="centered",
                   page_icon=str(Path(__file__).parent / "assets" / "icon.png"))
set_style(dark=True)                        # one look for every figure the api returns
st.markdown(
    """
    <style>
    [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer {visibility: hidden;}
    .block-container {max-width: 760px; padding-top: 1.6rem; padding-bottom: 3rem;}

    /* one accent (see paramost/.streamlit/config.toml): calm blue for fills, a lighter tint for text */
    :root { --accent-ink: #a8cfe6; --line: #383835; --grey: #c2c1bb; }

    h1 {font-size: 2rem; letter-spacing: -0.01em; margin-bottom: 0.15rem;}
    .lede {color: var(--grey); font-size: 0.98rem; line-height: 1.5; margin: 0 0 1.1rem;}

    /* readable grey for every caption, including the "how to read it" lines */
    [data-testid="stCaptionContainer"] p {color: var(--grey) !important; opacity: 1 !important;
      font-size: 0.86rem; line-height: 1.5;}

    /* the view selector as a navigation bar, with a clear active state */
    [data-testid="stButtonGroup"] {margin: 0.15rem 0 0.9rem;}
    [data-testid="stButtonGroup"] [role="radiogroup"] {display: flex; flex-wrap: wrap; gap: 4px;
      width: 100%; padding: 4px; border: 1px solid var(--line); border-radius: 8px;
      background: #232321;}
    [data-testid="stButtonGroup"] button[data-variant="segmented_control"] {flex: 1 1 auto;
      justify-content: center; border: 1px solid transparent; border-radius: 5px;
      padding: 5px 12px; color: #b9b8b2;}
    [data-testid="stButtonGroup"] button[data-variant="segmented_control"]:hover {color: #f0efec;}
    [data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected="true"] {
      background: rgba(53, 113, 154, 0.24); border-color: rgba(120, 176, 210, 0.55);
      color: var(--accent-ink);}

    /* a little more room around the controls and the pictures */
    [data-testid="stSlider"], [data-testid="stSelectbox"], [data-testid="stRadio"],
    [data-testid="stCheckbox"], [data-testid="stToggle"] {margin-top: 0.15rem;}
    [data-testid="stImage"], [data-testid="stPyplot"] {margin: 0.35rem 0 0.25rem;}
    [data-testid="stImage"] img {max-width: 100%; height: auto;}
    [data-testid="stVerticalBlockBorderWrapper"] {border-radius: 8px;}

    .app-footer {margin-top: 2.2rem; padding-top: 0.9rem; border-top: 1px solid var(--line);
      color: #9d9c96; font-size: 0.8rem; line-height: 1.6;}
    .app-footer a {color: var(--accent-ink); text-decoration: none;}
    .app-footer a:hover {text-decoration: underline;}

    /* phones: keep everything inside the screen */
    @media (max-width: 480px) {
      .block-container {padding-left: 0.85rem !important; padding-right: 0.85rem !important;
        padding-top: 1.1rem !important;}
      h1 {font-size: 1.6rem;}
      .lede {font-size: 0.92rem;}
      [data-testid="stButtonGroup"] button[data-variant="segmented_control"] {font-size: 0.8rem;
        padding: 5px 7px;}
      [data-testid="stCaptionContainer"] p {font-size: 0.82rem;}
      [data-testid="stImage"] img, iframe {max-width: 100% !important;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

q = st.query_params
LIVE = True                                 # set from the Offline toggle on every run (first_setup, page)


def initial_offline():
    """The Offline toggle at first load: ?offline=1/0 in the link, else the older ?live=1/0,
    else SPHEREX_DEMO=1 (a server open to visitors starts offline), else live (local use)."""
    if q.get("offline") in ("0", "1"):
        return q.get("offline") == "1"
    if q.get("live") in ("0", "1"):
        return q.get("live") == "0"
    return os.environ.get("SPHEREX_DEMO", "0") == "1"


# ------------------------------------------------------------------ helpers
def call(fn, *args, **kwargs):
    """Every api call goes through here: one lock for the whole app. Demo (offline) mode is one
    switch for the whole process, so it is set for this visitor's choice inside the lock."""
    with LOCK:
        api.set_demo_mode(not LIVE)
        return fn(*args, **kwargs)


# Measured 16 Nov 2026, 62 new cutouts from IRSA: 1 worker 799 s (12.9 s per image), 6 workers
# 110 s (7.3x faster). IRSA's speed varies, so the estimate uses 13 s and a 6x speed-up.
SECONDS_PER_IMAGE = 13.0
PARALLEL_SPEEDUP = {1: 1.0, 6: 6.0}         # workers -> speed-up; other counts: 0.75 x workers


def download_time(n):
    """Rough time for n new images at the current number of download workers -> 'about 1-2 min'."""
    workers = min(download_workers(), max(n, 1))
    speedup = PARALLEL_SPEEDUP.get(workers, max(1.0, 0.75 * workers))
    seconds = n * SECONDS_PER_IMAGE / speedup
    lo, hi = seconds * 0.7, seconds * 1.5
    if hi < 60:
        return "under a minute"
    if lo < 60:
        return f"about 1-{max(2, round(hi / 60))} min"
    return f"about {int(lo // 60)}-{max(int(lo // 60) + 1, round(hi / 60))} min"


def count_missing(fn, *args, **kwargs):
    """Live mode: how many images fn(*args, **kwargs) would download (api.count_downloads), or 0.
    The archive not answering (searching a new target) raises ArchiveDown: guarded() says so
    once, instead of the view trying the same search again. Other failures give 0: the real
    call then shows its own message."""
    if not LIVE:
        return 0
    try:
        with st.spinner("checking which images are downloaded..."):
            return call(api.count_downloads, fn, *args, **kwargs)["missing"]
    except (OSError, TimeoutError) as e:
        raise ArchiveDown(str(e)) from None
    except Exception:
        return 0


def download_note(n, what="this"):
    """One line before a long call: how many images it will download and how long that takes."""
    st.info(f"{what} needs {plural(n, 'image')} from IRSA that {'is' if n == 1 else 'are'} not "
            f"downloaded yet ({download_time(n)}). Turn on Offline to see only downloaded data.")


def download_gate(key, fn, *args, **kwargs):
    """For views that load by themselves: True when nothing has to be downloaded (or Offline is
    on), or in the run where the Download button was pressed; otherwise shows the count with the
    button and returns False, so nothing starts automatically."""
    n = count_missing(fn, *args, **kwargs)
    if not n:
        return True
    download_note(n, "this view")
    return st.button(f"download {plural(n, 'image')}", key=f"dl|{key}", type="primary")


def guarded(panel):
    """Build one panel. The api writes its ValueError messages for users, so show those as
    they are; anything else becomes one short sentence. True if the panel worked."""
    try:
        panel()
        return True
    except ValueError as e:
        msg = str(e).replace(" Demo mode uses only images already in cache/.",
                             " Offline is on: only downloaded images are used.")
        # api._epochs uses this wording when demo mode has no cached images for the request
        if api.demo_mode() and "offline cache" in msg:
            st.warning(msg.replace("Untick demo mode", "Turn off Offline at the top"))
        else:
            st.error(msg)
    except (ArchiveDown, OSError, TimeoutError) as e:
        st.warning(ARCHIVE_DOWN.format(detail=str(e)[:160]))
    except Exception:
        st.error("This part could not be made. The data may not be downloaded yet; "
                 "try again or pick another setting.")
    return False


class ArchiveDown(Exception):
    """NASA's archive did not answer while counting what a view needs."""


ARCHIVE_DOWN = ("NASA's archive (IRSA) is not answering right now ({detail}). Try again in a few "
                "minutes; targets you have downloaded open with Offline on.")


SHOW_PROGRESS_AFTER_S = 0.5               # a cached result returns sooner, so it never flashes a bar


class ProgressLine:
    """The api's progress(stage, done, total) callback: a bar and one caption line, e.g.
    "downloading images · 23 / 61 · about 2 min left", drawn in a placeholder at the place it was
    created, once the call has taken SHOW_PROGRESS_AFTER_S. The api calls it in this script run's
    thread, so every update reaches the page while the computation is still running.
    The calls come from inside st.cache_data functions, and Streamlit records anything drawn there
    to replay it on a cache hit, where this placeholder no longer exists (the replay fails). So
    the drawing runs in the context captured here, outside the cached function: not recorded."""

    def __init__(self):
        self._box = st.empty()
        self._context = contextvars.copy_context()
        self._estimate = Estimate()
        self._start = time.monotonic()
        self._bar = self._line = None

    def __call__(self, stage, done, total):
        info = self._estimate.update(stage, done, total)
        if time.monotonic() - self._start >= SHOW_PROGRESS_AFTER_S:
            self._context.run(self._draw, info)

    def _draw(self, info):
        if self._bar is None:
            box = self._box.container()
            self._bar, self._line = box.empty(), box.empty()
        self._bar.progress(info["fraction"])
        self._line.caption(info["text"])

    def clear(self):
        self._box.empty()


def with_progress(run):
    """run(progress) with a new ProgressLine; the bar and its line are removed when the result
    (or an error) arrives."""
    line = ProgressLine()
    try:
        return run(line)
    finally:
        line.clear()


# Sky-viewer backgrounds: label, survey ID, and the HiPS servers to try in order.
# Since about 2026-11-09 CDS (Strasbourg) has been handling a cybersecurity incident and its
# image-survey server alasky.cds.unistra.fr answers 404 for every survey; status and the CDS list of
# mirrors: https://cds.unistra.fr/ . aladin-lite 3.6.1 also looks survey IDs up on
# alasky.unistra.fr / alaskybis.unistra.fr, which do not resolve or answer, so an ID alone shows a
# grey canvas. Until alasky recovers we pass mirror URLs (checked 2026-11-17: properties, allsky
# and tiles all 200). Once it does, go back to the IDs (CDS/P/allWISE/color, ...) as `survey`.
ALADIN_SURVEYS = [
    ("WISE colour", "CDS/P/allWISE/color", ["https://skies.esac.esa.int/AllWISEColor",
                                            "https://irsa.ipac.caltech.edu/data/hips/CDS/AllWISE/RGB-W4-W2-W1"]),
    ("2MASS colour", "CDS/P/2MASS/color", ["https://skies.esac.esa.int/2MASSColor",
                                           "https://irsa.ipac.caltech.edu/data/hips/CDS/2MASS/Color"]),
    ("DSS colour", "CDS/P/DSS2/color", ["https://skies.esac.esa.int/DSSColor",
                                        "https://irsa.ipac.caltech.edu/data/hips/CDS/DSS2/color"]),
]
ALADIN_TILE_TIMEOUT_S = 10      # per server: no tile within this time -> next server, then the message

ALADIN_HTML = """<!doctype html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#1a1a19;color:#f0efec;font:13px system-ui, sans-serif">
<div id="bar" style="display:none;height:26px;align-items:center;gap:6px">
  <label for="survey">background</label><select id="survey"></select></div>
<div id="wrap" style="position:relative">
  <div id="aladin" style="width:100%;height:420px">Loading sky viewer…</div>
  <div id="down" style="display:none;position:absolute;inset:0;z-index:100;background:#1a1a19;
       flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:16px">
    <div>Sky viewer unavailable (survey server down)</div>
    <div style="opacity:.7;margin-top:6px">CDS, which normally serves these images, has an outage
      (Nov 2026), and the mirror servers did not answer either.</div></div>
</div>
<script type="module">
  const SURVEYS = __SURVEYS__, TIMEOUT_MS = __TIMEOUT_MS__;
  const box = document.getElementById("aladin"), down = document.getElementById("down");
  // Server prefixes that have delivered at least one tile (HTTP 200). Browsers without
  // responseStatus report undefined: counted as delivered, so they never show a false alarm.
  const served = new Set();
  new PerformanceObserver(list => {
    for (const e of list.getEntries()) {
      const i = e.name.indexOf("/Norder");
      if (i > 0 && (e.responseStatus === undefined || e.responseStatus === 200)) served.add(e.name.slice(0, i));
    }
  }).observe({type: "resource", buffered: true});
  // This try/catch only covers loading the script and starting Aladin (no network, no WebGL2).
  // Aladin fetches the survey and its tiles later, asynchronously, and reports nothing back when
  // that fails, so the watchdog below checks that a tile actually arrived.
  let A, a, url;
  const start = (u, target, fov) => {     // a new Aladin view on server u
    box.textContent = "";
    a = A.aladin('#aladin', {target: target, fov: fov, survey: u,
      showReticle: true, showLayersControl: false});
    const c = A.catalog({name: 'target', sourceSize: 14, color: 'red'});
    a.addCatalog(c);
    c.addSources([A.source(__RA__, __DEC__, {name: __NAME__})]);
    url = u;
  };
  try {
    ({ default: A } = await import("https://cdn.jsdelivr.net/npm/aladin-lite@3.6.1/dist/aladin.js"));
    await A.init;
    start(SURVEYS[0].urls[0], __TARGET__, __FOV__);
  } catch (e) {
    a = null;
    box.textContent = "Sky viewer unavailable";
  }
  if (a) {
    // Switch servers. When the current one never delivered a tile, Aladin is still waiting on it
    // (and on its own fallback survey at CDS, which hangs), and a new layer queues behind that:
    // so start a new view at the same centre and zoom instead of changing the layer.
    const use = u => {
      if (served.has(url)) { a.setBaseImageLayer(u); url = u; }
      else { const [ra, dec] = a.getRaDec(); start(u, ra + " " + dec, a.getFov()[0]); }
    };
    let run = 0;
    const show = (s, first) => {          // try each server of survey s in turn
      const me = ++run;
      down.style.display = "none";
      const attempt = k => {
        if (!first || k > 0) use(s.urls[k]);
        setTimeout(() => {
          if (me !== run || served.has(s.urls[k])) return;
          if (k + 1 < s.urls.length) attempt(k + 1);
          else down.style.display = "flex";
        }, TIMEOUT_MS);
      };
      attempt(0);
    };
    const sel = document.getElementById("survey");
    SURVEYS.forEach((s, i) => sel.add(new Option(s.label, i)));
    sel.onchange = () => show(SURVEYS[sel.value], false);
    document.getElementById("bar").style.display = "flex";
    show(SURVEYS[0], true);
  }
</script></body></html>"""


def _js(value):
    """A Python value as a JavaScript literal that is safe inside <script> (no "</script>")."""
    return json.dumps(value).replace("</", "<\\/")


def aladin_html(ra, dec, name, fov):
    """The sky-viewer page for one position; fov in arcmin (None: 15 arcmin)."""
    surveys = [{"label": label, "id": sid, "urls": urls} for label, sid, urls in ALADIN_SURVEYS]
    return (ALADIN_HTML.replace("__SURVEYS__", _js(surveys))
            .replace("__TIMEOUT_MS__", str(int(ALADIN_TILE_TIMEOUT_S * 1000)))
            .replace("__TARGET__", _js(f"{ra} {dec}"))
            .replace("__FOV__", repr(float(fov) / 60 if fov else 0.25))
            .replace("__RA__", repr(float(ra))).replace("__DEC__", repr(float(dec)))
            .replace("__NAME__", _js(name)))


def sky_panel(text, fov):
    """Optional Aladin Lite viewer (WISE, 2MASS or DSS colour images) around the resolved position."""
    with st.expander("Sky around this target (Aladin Lite)", expanded=False):
        try:
            info = call(api.resolve, text)
        except Exception:
            st.caption("sky viewer unavailable: the target could not be resolved.")
            return
        embed_html(aladin_html(float(info["ra"]), float(info["dec"]), info["name"], fov), height=450)
        st.caption("Background images are from WISE, 2MASS or DSS, not SPHEREx, and are years older, "
                   "so fast-moving stars may look offset.")


def share_view():
    """'Share this view': the link that reopens this target with these settings (ra/dec added,
    so it also works for any position). Base URL from SPHEREX_PUBLIC_URL if it is set."""
    params = st.query_params.to_dict()
    try:
        info = call(api.resolve, st.session_state["target"])
        params["ra"], params["dec"] = f"{info['ra']:.5f}", f"{info['dec']:.5f}"
    except Exception:
        pass
    tail = "?" + urlencode(params)
    base = os.environ.get("SPHEREX_PUBLIC_URL", "").rstrip("/")
    st.caption("share this view")
    st.code(f"{base}/{tail}" if base else tail, language=None)


def show(fig):
    st.pyplot(fig)
    plt.close(fig)                          # free the figure; matplotlib keeps every one open


def guarded_call(fn, *args, **kwargs):
    """One api call with guarded()'s error wording -> its result, or None on failure. Used
    where a failing picture must not remove the widgets below it."""
    box = {}
    if guarded(lambda: box.update(result=call(fn, *args, **kwargs))):
        return box["result"]
    return None


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
    """detector/band/tolerance for a target. `live` is only part of the cache key: when live, a
    name lookup may reach the network, so the two modes must not share a result. No target (the
    start screen): the general defaults, without a name lookup."""
    if not text.strip():
        return dict(api.OTHER_DEFAULTS)
    return call(api.defaults, text)


@st.cache_data(show_spinner=False, max_entries=12)
def cached_player(text, detector, fov, mode, wl, fps, live, clip, days, pictures, real_time, _progress=None):
    """The interactive player as one HTML page. `live` is only part of the cache key: live mode
    may see other data. clip=False and each time step (days) are different sets of pictures;
    pictures is None (all) or a tuple of rows of api.epochs. real_time: hold each picture in
    proportion to the gap to the next one; the app's checkbox sets it, so the player's own
    checkbox is hidden. _progress: a ProgressLine (not part of the cache key)."""
    html = call(api.player_html, text, detector, fov, mode, fps, wl, days, width=600, clip=clip,
                pictures=pictures, real_time=real_time, show_real_time_toggle=False, progress=_progress)
    # show_real_time_toggle=False marks the player's own checkbox row with `hidden`, but the
    # player's `.bar {display:flex}` rule overrides that attribute, so it would stay visible
    # next to the app's checkbox. Force the row off (library CSS, not ours to change).
    return html.replace("<style>", "<style>.bar[hidden]{display:none}", 1)


@st.cache_data(show_spinner=False, max_entries=8)
def cached_flipbook(text, detector, fov, mode, wl, fps, live, clip, days, pictures, _progress=None):
    """GIF bytes for the export button. Same key rule as the player."""
    return call(api.flipbook, text, detector, fov, mode, fps, wl, days, clip=clip, pictures=pictures,
                progress=_progress)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_epochs(text, detector, fov, wl, clip, days, pictures, live, _progress=None):
    """One row per picture of the player with these settings (api.epochs; pictures as for the
    player). It shares the stacks the player builds, so it costs nothing extra."""
    return call(api.epochs, text, detector, fov, wl, days, clip, pictures, progress=_progress)


@st.cache_data(show_spinner=False, max_entries=8)
def cached_visits(text, live):
    """One row per SPHEREx visit, for the spectrum's visit picker. Without a detector this
    only reads the cached frame tables, so it does not stack images."""
    return call(api.visits, text)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_visits_fresh(text, stamp, live):
    """visits() after "check for new data". `stamp` goes up on every press, so the table from
    before the check never answers it; `live` keeps demo and live results apart."""
    return call(api.visits, text, refresh=True)


def bump_refresh(text):
    """Button callback for "check for new data": runs before the rerun, so the table section
    above the button already sees the new stamp. A new target starts again from zero."""
    seen, stamp = st.session_state.get("data_stamp", (None, 0))
    st.session_state["data_stamp"] = (text, stamp + 1 if seen == text else 1)


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
        return api.OTHER_DEFAULTS["detector"]


def picture_counts(text, detector, fov, wl, clip, days, pictures):
    """api.epochs meta for these settings: n_pictures, n_frames_total, n_few_frames (pictures
    resting on fewer than 4 frames under the centre), plus releases (sorted names) and newest (last
    frame date), or None. api.epochs shares the stacks the player already built, so this is one
    cheap call. A failure here drops the line, never the video."""
    try:
        table = cached_epochs(text, detector, fov, wl, clip, days, pictures, LIVE)
    except Exception:
        return None
    counts = dict(table.meta)
    releases = {r.strip() for row in table["releases"] for r in str(row).split(",") if r.strip()}
    counts["releases"] = sorted(releases)
    counts["newest"] = max(table["last_date"]) if len(table) else None
    return counts


def choose_pictures(text, detector, fov, wl, clip, days):
    """The "choose pictures" box, filled from api.epochs -> None (all pictures), or a sorted
    tuple of the chosen rows. Above MAX_PICK pictures the box is hidden (None).
    The box has its own key per setting, so a choice never carries over to other pictures."""
    table = with_progress(lambda p: cached_epochs(text, detector, fov, wl, clip, days, None, LIVE, _progress=p))
    n = len(table)
    if n > MAX_PICK:
        st.caption("choose a coarser time step to pick pictures")
        return None
    rows = list(range(n))
    chosen = st.multiselect(
        "choose pictures", rows, default=rows,
        format_func=lambda i: f"{table['date'][i]} ({plural(int(table['n_frames'][i]), 'frame')})",
        key="pics|" + "|".join(str(x) for x in (text, detector, fov, wl, clip, days)))
    return None if len(chosen) == n else tuple(sorted(chosen))


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


START_HINT = ("Type a star name or coordinates. The first view downloads from NASA's archive "
              "(about 1-3 min); after that it opens instantly.")

EVERY_FRAME_NOTE = ("single exposures: brightness flickers because each frame sees a slightly "
                    "different wavelength; fast movers such as asteroids show here and not in "
                    "stacked pictures.")

# One grey line at the top of each view: what it does and what to try.
VIEW_INTRO = {
    "video": "the flipbook: the same patch of sky, one picture per visit or time step, played in "
             "order. try play, the arrows, or difference mode to see what changed between visits.",
    "compare": "single pictures of the same patch: all visits added, later minus earlier, one "
               "detector minus another, and three detectors as a colour picture. use the pickers "
               "to change which visits are compared.",
    "overlays": "the picture with catalogue stars drawn on top: Gaia positions and motions, "
                "CatWISE sources, and the target's predicted position. untick a catalogue to see "
                "which markers it adds.",
    "light curve": "the target's brightness over time at one wavelength. press measure; a smaller "
                   "tolerance compares light of nearly the same colour only.",
    "spectrum": "the brightness at every wavelength in one visit, so the object's colour can be "
                "read off. press measure; tick every visit to compare the shapes.",
    "data": "the visits table, one exposure with its flagged pixels, and a check for new data. the "
            "table shows which detectors have frames in each visit.",
    "about": "what the tool shows, how to read the pictures, what they cannot show, and a "
             "glossary. start here if a word or a picture is unclear.",
}

# Under every picture whose axes are RA and Dec (the library draws them on a north-up sky grid).
AXES_LINE = ("the picture is a small patch of sky. the horizontal axis is RA (right ascension) and "
             "the vertical axis is Dec (declination): the sky's version of longitude and latitude. "
             "north is up and east is to the left, so RA numbers get smaller to the right.")


def intro(view):
    """The grey line at the top of a view (appearance only: it calls nothing)."""
    st.caption(VIEW_INTRO[view])


def axes_note():
    """The grey line under a picture whose axes are RA and Dec."""
    st.caption(AXES_LINE)


# ------------------------------------------------------------------ state
def url_warn(text):
    """Remember one problem with the link; shown once at the top of the page."""
    st.session_state.setdefault("_url_warnings", []).append(text)


def url_target():
    """Target from the link: ?target=<name>, else ?ra=<deg>&dec=<deg>, else none (the start
    screen). Coordinates that are not numbers or out of range are ignored with a warning."""
    name = (q.get("target") or "").strip()
    if name:
        return name
    ra, dec = q.get("ra"), q.get("dec")
    if ra is None and dec is None:
        return ""
    try:
        ra, dec = float(ra), float(dec)
        if not (0 <= ra < 360 and -90 <= dec <= 90):
            raise ValueError
    except (TypeError, ValueError):
        url_warn("the ra/dec in the link are not valid coordinates (ra 0-360, dec -90 to 90 degrees), "
                 "so they were ignored.")
        return ""
    return f"{ra} {dec}"


def first_setup():
    """Fill st.session_state once, starting from the URL."""
    global LIVE
    if "target" in st.session_state:
        return
    st.session_state["offline"] = initial_offline()
    LIVE = not st.session_state["offline"]
    st.session_state["target"] = url_target()
    if "fov" in q:
        try:
            float(q["fov"])
        except (TypeError, ValueError):
            url_warn(f"the field of view in the link ({q['fov']!r}) is not a number, so 4 arcmin is used.")
    sug = api.OTHER_DEFAULTS
    try:                                    # api.defaults returns OTHER_DEFAULTS for unknown input
        sug = cached_defaults(st.session_state["target"], LIVE)
    except Exception:
        pass
    st.session_state["detector"] = q.get("detector", sug["detector"])
    st.session_state["wl"] = q.get("wl", "")
    st.session_state["fov"] = url_fov()
    st.session_state["view"] = q.get("view") if q.get("view") in VIEWS else "video"
    st.session_state["mode"] = q.get("mode") if q.get("mode") in MODES else "normal"
    st.session_state["raw"] = q.get("clip") == "0"      # ?clip=0 -> plain average of the frames
    st.session_state["days"] = url_days()               # time step; not a widget key, so it survives view changes
    st.session_state["real_time"] = q.get("rt") == "1"  # player holds each picture for its time gap
    st.session_state["_defaults_for"] = st.session_state["target"]


def refresh_defaults():
    """Target changed (typed or a button): put that target's cached settings back."""
    target = st.session_state["target"]
    if st.session_state.get("_defaults_for") == target:
        return
    try:
        sug = cached_defaults(target, LIVE)
    except Exception:
        sug = api.OTHER_DEFAULTS
    st.session_state["detector"] = sug["detector"]
    st.session_state["wl"] = ""
    st.session_state["_defaults_for"] = target


# ------------------------------------------------------------------ your targets
MAX_TARGET_BUTTONS = 12
# a server open to visitors (SPHEREX_DEMO=1) shows its targets, but no visitor may delete its data
REMOVE_ALLOWED = os.environ.get("SPHEREX_DEMO", "0") != "1"
PRELOAD_TARGETS, PRELOAD_FILES = 3, 4      # most recent targets, newest saved results of each


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def view_settings(view):
    """The settings of the view on screen, as in the link (what 'last viewed with' means)."""
    return {"detector": st.session_state["detector"], "wl": st.session_state["wl"],
            "fov": f"{float(st.session_state['fov']):.1f}", "view": view,
            "mode": st.session_state.get("mode", "normal"), "clip": "0" if st.session_state["raw"] else "1",
            "days": str(st.session_state.get("days", 60)), "rt": "1" if st.session_state.get("real_time") else "0"}


def remember_view(view):
    """After a view was shown: update this target's entry in <cache>/targets.json (images, size,
    settings, date). Only when the target or settings changed, or every 30 s, so a rerun does
    not rescan the cache; a target without downloaded images is not added."""
    text = st.session_state["target"].strip()
    settings = view_settings(view)
    sig = (text, json.dumps(settings, sort_keys=True))
    last = st.session_state.get("_recorded")
    if last and last[0] == sig and time.time() - last[1] < 30:
        return
    st.session_state["_recorded"] = (sig, time.time())
    try:
        files = call(api.target_files, text)
        info = call(api.resolve, text)
        key = results.safe_name(files["name"])
        if files["n_images"] or key in targets_index.read(CACHE_ROOT):
            targets_index.record(CACHE_ROOT, key, name=info["name"], text=text, ra=info["ra"], dec=info["dec"],
                                 settings=settings, n_images=files["n_images"], size_bytes=files["size_bytes"])
    except Exception:
        pass                                   # the index only speeds up the start screen


def not_downloaded_offline():
    """Offline and nothing of this target on this computer (no frame list or no images): say so
    and skip the view, instead of trying the archive (offline) and failing. -> True if shown."""
    if LIVE:
        return False
    try:
        files = call(api.target_files, st.session_state["target"].strip())
    except Exception:
        return False                    # the view shows its own message
    if files["frame_list"] is not None and files["n_images"]:
        return False
    st.info(f"Not downloaded yet: there are no images of {st.session_state['target'].strip()} on this "
            "computer. Turn off Offline at the top to download them (the first view takes about "
            "1-3 min; after that it opens instantly).")
    return True


def open_target(entry):
    """A 'your targets' button: that target with the settings it was last viewed with."""
    st.session_state["target"] = entry["text"]
    st.session_state["_defaults_for"] = entry["text"]     # keep these settings, not the defaults
    sug = api.OTHER_DEFAULTS
    try:
        sug = cached_defaults(entry["text"], LIVE)
    except Exception:
        pass
    got = entry.get("settings") or {}
    st.session_state["detector"] = got.get("detector", sug["detector"])
    st.session_state["wl"] = got.get("wl", "")
    try:
        st.session_state["fov"] = min(max(float(got.get("fov", 4.0)), 2.0), float(api.MAX_FOV))
    except (TypeError, ValueError):
        st.session_state["fov"] = 4.0
    st.session_state["view"] = got.get("view") if got.get("view") in VIEWS else "video"
    st.session_state["mode"] = got.get("mode") if got.get("mode") in MODES else "normal"
    st.session_state["raw"] = got.get("clip") == "0"
    try:
        days = int(got.get("days", 60))
    except (TypeError, ValueError):
        days = 60
    st.session_state["days"] = days if days in api.TIME_STEPS.values() else 60
    st.session_state["step"] = step_label(st.session_state["days"])   # the time-step box keeps its own state
    st.session_state["real_time"] = got.get("rt") == "1"
    st.session_state.pop("_remove", None)


def ask_remove(key):
    st.session_state["_remove"] = key


def cancel_remove():
    st.session_state.pop("_remove", None)


def do_remove(entry):
    """Delete the target's downloaded data and saved results, then its index entry."""
    st.session_state.pop("_remove", None)
    try:
        freed = call(api.remove_target, entry["text"])
    except Exception as e:
        st.session_state["_removed"] = ("error", f"{entry['name']} could not be removed ({type(e).__name__}); "
                                                 "try again with Offline off, so its name can be looked up.")
        return
    targets_index.drop(CACHE_ROOT, entry["key"])
    st.cache_data.clear()                      # pictures of it kept by this page
    st.session_state["_removed"] = ("ok", f"removed {entry['name']}: {human_size(freed)} freed.")


def your_targets():
    """The start screen's list: one button per target with downloaded images, newest first."""
    try:
        entries = targets_index.load_index(CACHE_ROOT)
    except Exception:
        entries = []
    kind, msg = st.session_state.pop("_removed", (None, None))
    if msg:
        (st.success if kind == "ok" else st.error)(msg)
    if not entries:
        return
    st.markdown("#### your targets")
    shown = entries if st.session_state.get("targets_all") else entries[:MAX_TARGET_BUTTONS]
    for e in shown:
        label = f"{e['name']}  ·  {e.get('last_viewed', '')[:10]}  ·  {human_size(e.get('size_bytes', 0))}"
        if REMOVE_ALLOWED:
            c1, c2 = st.columns([6, 1])
            c1.button(label, key=f"open|{e['key']}", on_click=open_target, args=(e,), use_container_width=True)
            c2.button("remove", key=f"rm|{e['key']}", on_click=ask_remove, args=(e["key"],),
                      help="Delete this target's downloaded images and saved results.")
        else:
            st.button(label, key=f"open|{e['key']}", on_click=open_target, args=(e,), use_container_width=True)
        if st.session_state.get("_remove") == e["key"]:
            st.warning(f"Delete {human_size(e.get('size_bytes', 0))} of downloaded data and saved results for "
                       f"{e['name']}? Viewing it again downloads everything again.")
            c1, c2 = st.columns(2)
            c1.button("yes, remove", key=f"rm_yes|{e['key']}", on_click=do_remove, args=(e,), type="primary")
            c2.button("cancel", key=f"rm_no|{e['key']}", on_click=cancel_remove)
    if len(entries) > MAX_TARGET_BUTTONS:
        st.toggle(f"show all {len(entries)}", key="targets_all")


def _preload():
    """Background: read the newest saved results of the most recent targets into memory.
    Disk only (spherex.results.preload never computes or downloads); any failure is ignored."""
    try:
        for e in targets_index.load_index(CACHE_ROOT)[:PRELOAD_TARGETS]:
            folder = CACHE_ROOT / "results" / e["key"]
            files = sorted(folder.glob("*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)
            results.preload(files[:PRELOAD_FILES])
    except Exception:
        pass


@st.cache_resource(show_spinner=False)
def start_preload():
    """Once per app process, started after the page is drawn, on a daemon thread: it never
    blocks a page or a request (st.cache_resource runs this once for all visitors).
    PARAMOST_PRELOAD=0 turns it off."""
    if os.environ.get("PARAMOST_PRELOAD", "1") == "0":
        return None
    t = threading.Thread(target=_preload, name="paramost-preload", daemon=True)
    t.start()
    return t


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
    # the player controls sit in one group, so they read as a control bar
    with st.container(border=True):
        mode = st.radio("mode", MODES, horizontal=True, key="mode")
        c1, c2 = st.columns([3, 2])
        fps = c1.slider("pictures per second", 1, 8, 3, key="fps",
                        help="Playback speed only; the pictures stay the same.")
        step = c2.selectbox("time step", STEPS,
                            index=STEPS.index(step_label(st.session_state["days"])),
                            key="step", help="One picture per visit, month, week or single frame "
                                             "(single frames show asteroids, but flicker).")
        st.session_state["days"] = api.TIME_STEPS[step]
        real_time = st.checkbox("real time gaps", key="real_time",
                                help="Hold each picture in proportion to the time until the next one (up to 6x).")
    text = st.session_state["target"].strip()
    detector = st.session_state["detector"].strip() or None
    wl = st.session_state["wl"].strip() or None
    fov = float(st.session_state["fov"])
    clip = not st.session_state["raw"]
    days = st.session_state["days"]
    if not download_gate("video|" + "|".join(str(x) for x in (text, detector, fov, wl, clip, days)),
                         api.epochs, text, detector=detector, fov=fov, wl=wl, days=days, clip=clip):
        return
    with st.spinner("building the pictures..."):
        pictures = choose_pictures(text, detector, fov, wl, clip, days)
    if pictures == ():
        st.info("choose at least one picture.")
        return
    key = (text, detector, fov, mode, wl, fps, LIVE, clip, days, pictures)

    with st.spinner("building the player..."):
        html = with_progress(lambda p: cached_player(*key, real_time, _progress=p))
    # the player is 600 px wide: a square picture, its title and the control bar measure 655 px
    # in Chromium; 680 leaves a small margin and no empty band below the controls
    embed_html(html, height=680)
    sky_panel(text, fov)
    counts = picture_counts(text, detector, fov, wl, clip, days, pictures)
    if counts:
        line = (f"{plural(counts['n_pictures'], 'picture')} from "
                f"{plural(counts['n_frames_total'], 'frame')}")
        if counts["n_few_frames"]:
            line += f", {plural(counts['n_few_frames'], 'picture')} built from few frames"
        st.caption(line + (". " + EVERY_FRAME_NOTE if days == 0 else ""))
        if counts["releases"]:
            st.caption(("data release" if len(counts["releases"]) == 1 else "data releases")
                       + f" used: {', '.join(counts['releases'])} · data as of {counts['newest']} "
                         "(newest frame shown)")
        if counts["n_few_frames"] and days != 0:     # every frame: all of them, said above
            st.warning(f"{api.FEW_FRAMES_NOTE}: some pictures here rest on fewer than 4 frames "
                       "under the centre, so one bad frame can survive in them.")
    st.caption(READ_PLAYER[mode])

    # the gif is only built when asked for; its bytes stay for as long as the settings do
    if st.button("export gif", key="export_gif"):
        with st.spinner("building the gif..."):
            st.session_state["gif"] = (key, with_progress(lambda p: cached_flipbook(*key, _progress=p)))
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
        # the asteroid lookup is a network query, so offline mode must not wait for it
        st.caption("asteroid positions need the network, so they are not drawn while Offline is on.")
    text, det, fov, days = (st.session_state["target"], target_detector(), float(st.session_state["fov"]),
                            st.session_state["days"])
    if not download_gate(f"overlays|{text}|{det}|{fov}|{days}", api.overlay_figure, text, det, fov,
                         gaia=False, wise=False, asteroids=False, days=days):
        return
    with st.spinner("querying catalogues..."):
        fig, notes = with_progress(lambda p: call(
            api.overlay_figure, st.session_state["target"], target_detector(),
            float(st.session_state["fov"]), gaia=gaia, wise=wise,
            asteroids=asteroids and LIVE, days=st.session_state["days"], progress=p))
    show(fig)
    if notes.get("few_frames"):         # the title says it too, but small and easy to miss
        st.warning(f"{api.FEW_FRAMES_NOTE}: this picture rests on fewer than 4 frames under "
                   "the centre, so one bad frame can survive in it.")
    st.caption(overlay_caption(gaia, wise, asteroids and LIVE))
    axes_note()
    if "verdict" in notes:             # only when both catalogues were asked for
        st.info(notes["verdict"])
    for failed in notes["failed"]:     # one warning per catalogue that could not be reached
        st.warning(f"overlay not available: {failed}")
    if notes.get("wise_halo_stars"):
        one = notes["wise_halo_stars"] == 1
        st.caption(f"{plural(notes['wise_halo_stars'], 'bright Gaia star')} near the target "
                   + ("has no WISE counterpart: its halo hides the WISE motions around it."
                      if one else
                      "have no WISE counterpart: their halos hide the WISE motions around them."))


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
              f"({plural(int(r['n_frames']), 'frame')})" for r in visits]
    if not labels:
        st.info("no visits with images for this target.")
        return
    idx = st.selectbox("visit", list(range(len(labels))), index=len(labels) - 1,
                       format_func=labels.__getitem__, disabled=every, key=f"spec_visit|{text}")   # per target: starts at its latest visit

    n = count_missing(api.spectrum_figure, text, visit=idx, all_visits=every)
    if n:
        download_note(n, "this spectrum")
    if not st.button(f"download {plural(n, 'image')} and measure" if n else "measure", key="spec_run"):
        return                                  # the spectrum is only measured on a press
    with st.spinner("measuring the spectrum..."):
        fig, table = with_progress(lambda p: call(api.spectrum_figure, text, visit=idx, all_visits=every,
                                                  progress=p))
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


LIGHT_CURVE_READ = ("each dot = one measurement; dots joined by a line = the average of one visit; "
                    "grey x = flagged, grey triangles = lower limits of a saturated star (its true "
                    "brightness is higher), open squares = not measured; gaps are times SPHEREx "
                    "did not look here.")


def light_curve_panel():
    """Brightness of the target over time at one wavelength. Both boxes start from the target's
    cached defaults (api.defaults). Their keys include the target: with one fixed key, Streamlit
    kept the box's old value when the target changed while the box was not on the page (another
    view was open), so a new target was measured at the old target's wavelength. A new target now
    gets new boxes that start at its own defaults."""
    text = st.session_state["target"].strip()
    try:
        sug = cached_defaults(text, LIVE)
    except Exception:
        sug = api.OTHER_DEFAULTS
    c1, c2 = st.columns(2)
    band = c1.number_input(
        "wavelength (micron)", min_value=0.75, max_value=5.0, step=0.05, format="%.2f",
        value=float(sug["band"]), key=f"band|{text}", help="The wavelength at which the target is measured. The default is the "
                         "one cached for this target.")
    # only frames within this window around the wavelength are measured; the library warns
    # above MAX_SAFE_TOL, so the box stops there (a wider window mixes wavelengths).
    tol = c2.number_input(
        "tolerance (micron)", min_value=0.005, max_value=float(api.MAX_SAFE_TOL), step=0.005,
        format="%.3f", value=float(sug["tol"]), key=f"tol|{text}",
        help=f"Only frames within ±{api.MAX_SAFE_TOL:g} micron of the wavelength are used. "
             "A wider window mixes wavelengths, which can look like variability, so this "
             "stops at the library's safe limit.")

    n = count_missing(api.light_curve_figure, text, band=float(band), tol=float(tol))
    if n:
        download_note(n, "this light curve")
    if not st.button(f"download {plural(n, 'image')} and measure" if n else "measure", key="lc_run"):
        return                              # the light curve is only measured on a press
    with st.spinner("measuring the light curve..."):
        fig, table = with_progress(lambda p: call(api.light_curve_figure, text, band=float(band), tol=float(tol),
                                                  progress=p))
    show(fig)
    warning = table.meta.get("warning")     # saturation, wide window, neighbours, mixed releases
    if warning:
        st.warning(warning)
    st.caption(LIGHT_CURVE_READ)
    df = table.to_pandas()
    st.dataframe(df, hide_index=True)
    st.download_button("download csv", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"light_curve_{slug(text)}.csv", mime="text/csv",
                       on_click="ignore")   # keep the figure on the page while the file downloads


COMPARE_READ_DEEP = ("deep: every visit added into one picture, so faint things stand out; the "
                     "green circle is where the target should be in the last visit.")
COMPARE_READ_PAIR = ("pair: later minus earlier, red = brighter later, blue = brighter earlier; "
                     "the green circle is where the target should be in the later visit.")


def epoch_labels(table):
    """Picker labels for an api.epochs table, like '2026-03-17 (visit 1, 18 frames)'; the
    'few frames' mark matches the warning shown under the picture."""
    labels = []
    for r in table:
        label = f"{r['date']} (visit {int(r['visit'])}, {plural(int(r['n_frames']), 'frame')}"
        if r["few_frames"]:
            label += ", few frames"
        labels.append(label + ")")
    return labels


def compare_panel():
    """Deep picture (all visits added), a pair difference, and on a button press the band
    difference and the colour picture. All four use the app's detector, fov, wl, clip and days."""
    text = st.session_state["target"].strip()
    detector = st.session_state["detector"].strip() or None
    wl = st.session_state["wl"].strip() or None
    fov = float(st.session_state["fov"])
    clip = not st.session_state["raw"]
    days = st.session_state["days"]

    # the deep picture is the whole set of visits, so it loads with the view
    if not download_gate("compare|" + "|".join(str(x) for x in (text, detector, fov, wl, clip, days)),
                         api.epochs, text, detector=detector, fov=fov, wl=wl, days=days, clip=clip):
        return
    table = with_progress(lambda p: cached_epochs(text, detector, fov, wl, clip, days, None, LIVE, _progress=p))
    with st.spinner("adding the visits..."):
        fig = with_progress(lambda p: call(api.picture, text, kind="deep", detector=detector, fov=fov, wl=wl,
                                           clip=clip, days=days, progress=p))
    show(fig)
    if table.meta.get("n_few_frames"):
        n_few = int(table.meta["n_few_frames"])
        st.warning(f"{api.FEW_FRAMES_NOTE}: "
                   + ("one of the pictures" if n_few == 1 else f"{n_few} of the pictures")
                   + " added here " + ("rests" if n_few == 1 else "rest")
                   + " on fewer than 4 frames under the centre, so one bad frame can survive "
                     "in the deep picture.")
    st.caption(COMPARE_READ_DEEP)
    axes_note()

    # pair: rows of api.epochs (in time order) are the a and b of picture(kind="pair"); the api
    # draws the later picture minus the earlier one whichever order they are picked in. The keys
    # hold the target and settings, so a new target starts again at latest minus first.
    st.markdown("#### difference of two visits")
    labels = epoch_labels(table)
    rows = list(range(len(table)))
    settings = "|".join(str(x) for x in (text, detector, fov, wl, clip, days))
    c1, c2 = st.columns(2)
    b = c1.selectbox("earlier", rows, index=0, format_func=labels.__getitem__,
                     key="cmp_b|" + settings, help="The picture subtracted (blue = brighter then).")
    a = c2.selectbox("later", rows, index=len(rows) - 1, format_func=labels.__getitem__,
                     key="cmp_a|" + settings, help="The picture kept (red = brighter now).")
    if len(rows) > 1 and a != b:
        early, late = sorted((a, b))
        st.caption(f"showing {table['date'][late]} minus {table['date'][early]}"
                   + (" (the two were picked the other way round; the later one is always kept)"
                      if a < b else "") + ".")
    with st.spinner("subtracting the two visits..."):
        fig = with_progress(lambda p: guarded_call(api.picture, text, kind="pair", detector=detector, fov=fov,
                                                   wl=wl, clip=clip, days=days, a=a, b=b, progress=p))
    if fig is not None:                 # a == b: the api says so, and the section below stays
        show(fig)
        if table["few_frames"][a] or table["few_frames"][b]:
            st.warning(f"{api.FEW_FRAMES_NOTE}: one of the two pictures rests on fewer than 4 "
                       "frames under the centre, so one bad frame can survive in the difference.")
        st.caption(COMPARE_READ_PAIR)
        axes_note()

    # band difference and colour picture: each needs several detectors. Only detectors with
    # frames for this target are offered; the first choices are the ones the demo pictures were
    # made with (D6 minus D2, and D6, D3, D1 as red, green, blue).
    st.markdown("#### colour pictures")
    visits = cached_visits(text, LIVE)      # frame counts per detector; no stacking
    dets = [d for d in ("D1", "D2", "D3", "D4", "D5", "D6")
            if sum(int(r[d]) for r in visits) > 0]
    st.caption("detectors with frames for this target: " + (", ".join(dets) or "none") + ".")

    if len(dets) < 2:
        st.caption("a band difference needs two detectors.")
    else:
        c1, c2 = st.columns(2)
        long_det = c1.selectbox("long wavelength detector", dets,
                                index=dets.index("D6") if "D6" in dets else len(dets) - 1,
                                key=f"cmp_long|{text}")
        short_det = c2.selectbox("short wavelength detector", dets,
                                 index=dets.index("D2") if "D2" in dets else 0,
                                 key=f"cmp_short|{text}")
        n = sum(count_missing(api.epochs, text, detector=d, fov=fov, days=days, clip=clip)
                for d in {long_det, short_det})
        if n:
            download_note(n, "the band difference")
        if st.button(f"download {plural(n, 'image')}, then band difference" if n else "band difference",
                     key="cmp_band"):
            if long_det == short_det:
                st.info("choose two different detectors for the band difference.")
            else:
                with st.spinner("subtracting the two detectors..."):
                    fig = with_progress(lambda p: guarded_call(
                        api.picture, text, kind="banddiff", detector=detector, fov=fov, wl=wl, clip=clip,
                        days=days, long=long_det, short=short_det, progress=p))
                if fig is not None:
                    show(fig)
                    st.caption(f"band difference: red = brighter in {long_det}, blue = brighter "
                               f"in scaled {short_det} (normal stars cancel); the green circle "
                               "is where the target should be.")
                    axes_note()

    if len(dets) < 3:
        st.caption("a colour picture needs three detectors.")
    else:
        # the api's defaults first, then whatever else is cached
        order = [d for d in ("D6", "D3", "D1") if d in dets]
        order += [d for d in dets if d not in order]
        c1, c2, c3 = st.columns(3)
        red = c1.selectbox("red", dets, index=dets.index(order[0]), key=f"cmp_red|{text}")
        green = c2.selectbox("green", dets, index=dets.index(order[1]), key=f"cmp_green|{text}")
        blue = c3.selectbox("blue", dets, index=dets.index(order[2]), key=f"cmp_blue|{text}")
        n = sum(count_missing(api.epochs, text, detector=d, fov=fov, days=days, clip=clip)
                for d in {red, green, blue})
        if n:
            download_note(n, "the colour picture")
        if st.button(f"download {plural(n, 'image')}, then colour picture" if n else "colour picture",
                     key="cmp_rgb"):
            if len({red, green, blue}) < 3:
                st.info("choose three different detectors for the colour picture.")
            else:
                with st.spinner("combining the three detectors..."):
                    fig = with_progress(lambda p: guarded_call(
                        api.picture, text, kind="rgb", detector=detector, fov=fov, wl=wl, clip=clip,
                        days=days, rgb=f"{red},{green},{blue}", progress=p))
                if fig is not None:
                    show(fig)
                    st.caption(f"colour picture: red = {red}, green = {green}, blue = {blue}; "
                               "the green circle is where the target should be.")
                    axes_note()


FLAGS_READ = ("left = the exposure as observed, right = the cleaned picture with masked pixels in "
              "red; the green circle is where the target should be. the table lists every flag "
              "present, the share of pixels it covers and whether it is masked.")


def data_panel():
    """The visits table, one exposure with its flags, and a button to look for new data. The
    table reads the cached frame lists, so it needs no download and no stacking."""
    text = st.session_state["target"].strip()

    st.markdown("#### visits")
    # a refresh belongs to one target only: a new target starts without one
    seen, stamp = st.session_state.get("data_stamp", (None, 0))
    stamp = stamp if (seen == text and LIVE) else 0     # a pressed refresh, live mode only
    with st.spinner("checking the archive..." if stamp else "loading the visits..."):
        table = cached_visits_fresh(text, stamp, LIVE) if stamp else cached_visits(text, LIVE)
    if table.meta.get("warning"):
        st.warning(table.meta["warning"])
    st.dataframe(table.to_pandas(), hide_index=True)

    st.markdown("#### one exposure")
    # flags_figure takes one detector; "all" and combinations fall back to their first one
    box = st.session_state["detector"].strip()
    det = box.split("+")[0] if box else "D2"
    if det not in (f"D{i}" for i in range(1, 7)):
        det = "D2"
    # rows of this table are in visit order, so the visits with this detector are numbered
    # 0, 1, ... in the same order as flags_figure's own visit numbers
    rows = [i for i, r in enumerate(table) if int(r[det]) > 0]
    if not rows:
        st.info(f"no {det} frames for this target.")
        return
    c1, c2 = st.columns(2)
    j = c1.selectbox(f"{det} visit", list(range(len(rows))), index=len(rows) - 1,
                     format_func=lambda k: f"visit {int(table['visit'][rows[k]])}: "
                                           f"{table['first_date'][rows[k]]}",
                     key=f"flag_visit|{text}|{det}")
    n = int(table[det][rows[j]])
    frame = c2.selectbox("frame", list(range(n)), index=0,
                         format_func=lambda k: f"frame {k}",
                         key=f"flag_frame|{text}|{det}|{int(table['visit'][rows[j]])}")

    if st.button("show exposure with flagged pixels", key="flag_show"):
        with st.spinner("loading the exposure..."):
            fig, flags = call(api.flags_figure, text, detector=det, visit=j, frame=frame)
        show(fig)
        st.caption(FLAGS_READ)
        st.dataframe(flags.to_pandas(), hide_index=True)

    st.markdown("#### new data")
    st.button("check for new data", key="data_refresh", disabled=not LIVE,
              on_click=bump_refresh, args=(text,))
    if not LIVE:
        st.caption("checking for new data needs the network: turn off Offline at the top.")


ABOUT_LIMITS = [
    ("bright stars", "a very bright star fills its pixels, so the middle of it is clipped. its "
                     "colour and shape there are not real, and a spectrum can only give a lower "
                     "limit, drawn as grey triangles."),
    ("neighbour stars", "another star close to the target can fall into the same measurement, so "
                        "a value may describe two stars together, not only the target."),
    ("mixed releases", "SPHEREx data comes in releases, and the visits here can come from "
                       "different ones. a small jump between visits can be the pipeline, not the "
                       "star itself."),
    ("stacks", "a stack adds frames together. that helps faint things and hides anything that "
               "moves or changes fast, such as a fast asteroid."),
    ("asteroids", "the positions of known asteroids are looked up online, so with Offline on "
                  "they are not drawn."),
]


GLOSSARY = [
    ("RA and Dec", "right ascension and declination: the sky's longitude and latitude. RA runs "
                   "from 0 to 24 hours and is read in hours, minutes and seconds; Dec runs from "
                   "−90 to +90 degrees and is read in degrees and arcminutes. north is up in the "
                   "pictures and east is to the left, so RA numbers get smaller to the right."),
    ("arcminute and arcsecond", "parts of a degree: one arcminute is 1/60 of a degree and one "
                                "arcsecond is 1/60 of an arcminute. the field of view here is a "
                                "few arcminutes across."),
    ("pixel size", "SPHEREx's own pixels cover about 6 arcseconds of sky (6.15). the pictures "
                   "here are resampled onto a 3 arcsecond grid, so in them a star moving about 3 "
                   "arcseconds shifts by one pixel."),
    ("proper motion", "the slow drift of a star across the sky, in milliarcseconds per year "
                      "(mas/yr). Barnard's Star moves about 10 arcseconds a year, one of the "
                      "fastest stars known."),
    ("wavelength (micron)", "the colour of infrared light, in micrometres (micron). SPHEREx "
                            "measures from about 0.75 to 5 microns, mostly beyond the red the eye "
                            "can see."),
    ("detector D1 to D6", "SPHEREx has six detector arrays, and each one covers a different part "
                          "of the wavelength range (D5 and D6 together, for example, span 3.8 to "
                          "5 microns). the same star can look different in different detectors."),
    ("visit", "one pass over this patch of sky: a stretch of frames taken minutes apart. SPHEREx "
              "returns about every six months, so a target has a few visits."),
    ("frame and stack", "a frame is one exposure. a picture here is usually a stack: many frames "
                        "of the same visit added together to reduce noise."),
    ("deep picture", "all visits added together: the faintest, cleanest view of the patch."),
    ("difference", "the earlier picture is subtracted from the later one, so things that did not "
                   "change cancel out. red means brighter later, blue means brighter earlier, so a "
                   "moving object shows as a red and blue pair."),
    ("saturated", "too bright for the detector, so the centre is clipped and its brightness is "
                  "only a lower limit (drawn as grey triangles)."),
    ("Gaia", "a star catalogue with very precise positions and motions (Gaia DR3). the circles "
             "and arrows in the overlays come from it."),
    ("CatWISE2020", "a catalogue of infrared sources from the WISE telescope. the squares in the "
                    "overlays come from it."),
    ("light curve", "brightness of the target over time at one wavelength."),
    ("spectrum", "brightness across wavelengths for one visit: it shows how the object's colour is "
                 "made up."),
    ("flux (mJy)", "flux, in millijansky (mJy), a standard unit for the brightness of astronomical "
                   "sources. the plots label the vertical axis in mJy."),
    ("raw average", "keeps every frame, so fast movers and flares survive, but single-frame "
                    "defects stay too."),
]


def about_panel():
    """Plain words about the mission, the pictures and what they cannot show. No api call, so
    nothing here needs the lock, the spinner or an error message."""
    st.markdown(
        "#### what spherex is\n"
        "SPHEREx is a NASA space telescope, launched in 2025. it photographs the whole sky in "
        "near-infrared light and splits that light into many narrow wavelength bands at once, "
        "so every exposure is a small picture of the sky with a low-resolution spectrum of "
        "every point in it. the sky is scanned several times, and that is what makes the "
        "flipbook possible."
    )
    st.markdown(
        "#### how to read the pictures\n"
        "each picture is one small patch of sky around the target. dark means little light, "
        "bright means a lot. the green circle is where the target should be at that moment, "
        "worked out from its measured motion. a stack is several frames added together, which "
        "makes faint things easier to see and fast things fainter. in difference pictures only "
        "what changed is coloured: red is brighter than the reference, blue is fainter."
    )
    st.markdown(
        "#### known limits\n"
        + "\n\n".join(f"**{name}**: {text}" for name, text in ABOUT_LIMITS)
    )
    st.markdown(
        "#### credits\n"
        "images and measurements: SPHEREx data from IRSA, the NASA/IPAC Infrared Science "
        "Archive.\n\n"
        "star positions and motions: Gaia DR3 (ESA).\n\n"
        "infrared catalogue stars: CatWISE2020.\n\n"
        "names, distances and cross-identifications: SIMBAD (CDS, Strasbourg)."
    )
    with st.expander("glossary"):
        st.markdown("\n\n".join(f"**{term}**: {text}" for term, text in GLOSSARY))


# ------------------------------------------------------------------ page
first_setup()
LIVE = not st.session_state.setdefault("offline", initial_offline())
st.title("SPHEREx Flipbook")
for _w in st.session_state.pop("_url_warnings", []):    # bad values in the link: said once, then ignored
    st.warning(_w)
st.markdown('<p class="lede">enter a name or coordinates to see how a patch of sky changes '
            'in SPHEREx images.</p>', unsafe_allow_html=True)

st.text_input("target (name or coordinates)", key="target",
              placeholder="Barnard's Star, WISE 0855, 133.795 -7.245",
              help="A name, or coordinates like 133.795 -7.245 (degrees) or "
                   "08h55m10.8s -07d14m42.5s.")

refresh_defaults()                  # before the detector box, so its state is already right

with st.expander("options"):
    st.text_input("detector(s): D1 to D6, D5+D6, or all", key="detector",
                  help="D1 to D6, a sum like D5+D6, or all. The default is the detector that is "
                       "already cached for this target. Each detector covers a different part of "
                       "the 0.75 to 5 micron range, so the same star can look different in each.")
    st.text_input("wavelength range in micron, for example 4.4-4.7 (optional)", key="wl",
                  help="Only light in this range is used, between 0.75 and 5 micron. Leave it "
                       "empty to use the detector box.")
    st.slider("field of view in arcmin", 2.0, float(api.MAX_FOV), step=0.5, key="fov",
              help="Width of the picture in arcminutes (one arcminute is 1/60 of a degree). "
                   "The default is 4.")
    st.toggle("raw average (no clipping)", key="raw",
              help="Plain average instead of the clipped mean: keeps flares and fast movers, and also defects.")

st.toggle("Offline (only use downloaded data)", key="offline",
          help="On: nothing is downloaded; views show what is already on this computer. "
               "Off: a view that needs new images says how many and waits for its Download button.")
LIVE = not st.session_state["offline"]
if not LIVE:
    st.caption("offline: only images already downloaded are shown.")

view = st.segmented_control("view", VIEWS, key="view", label_visibility="collapsed",
                            selection_mode="single") or "video"

if view == "about":
    intro("about")
    about_panel()                       # no api call: works before a target resolves
else:
    if not st.session_state["target"].strip():
        st.caption(START_HINT)          # the start screen: nothing loads until a target is typed
        your_targets()
        start_preload()
        st.stop()
    if not guarded(header):             # unknown target: one message, no view underneath
        st.stop()
    # worker processes for cleaning and aligning frames (SPHEREX_WORKERS): started now, in the
    # background, so a view that has to build stacks does not wait for their imports. A no-op
    # when they are already running; they stop after workers.IDLE_S seconds without work.
    workers.prestart()

    intro(view)                         # one grey line: what this view does, what to try
    if not_downloaded_offline():
        st.stop()
    panel = {"video": video_panel, "compare": compare_panel, "overlays": overlays_panel,
             "spectrum": spectrum_panel, "light curve": light_curve_panel, "data": data_panel}[view]
    if guarded(panel):
        remember_view(view)             # "your targets" on the start screen

# keep the link shareable (the older ?live= is replaced by ?offline=)
if "live" in st.query_params:
    del st.query_params["live"]
st.query_params.update(
    offline="1" if st.session_state["offline"] else "0",
    target=st.session_state["target"],
    detector=st.session_state["detector"],
    fov=f"{float(st.session_state['fov']):.1f}",
    wl=st.session_state["wl"],
    view=view,
    mode=st.session_state.get("mode", "normal"),
    clip="0" if st.session_state["raw"] else "1",
    days=str(st.session_state.get("days", 60)),
    rt="1" if st.session_state.get("real_time") else "0",
)

for _k in ("ra", "dec"):                   # used once on load; the target now holds the position
    if _k in st.query_params:
        del st.query_params[_k]
share_view()
start_preload()

st.markdown(
    '<div class="app-footer">SPHEREx / IRSA, Gaia DR3, CatWISE2020, SIMBAD'
    f' &nbsp;·&nbsp; <a href="{REPO_URL}" target="_blank" rel="noopener">{REPO_URL}</a></div>',
    unsafe_allow_html=True,
)
