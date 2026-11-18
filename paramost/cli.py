"""The `paramost` command: start the SPHEREx Flipbook app and look after its data cache.

    paramost                          open the app in the browser (live: downloads on request)
    paramost --offline                start with Offline on: only data already downloaded
    paramost --port 8502 --no-browser
    paramost --cache-dir D:\\spherex   use another cache folder (default: the user cache folder)
    paramost cache-info               where the cache is, its size, which targets are in it
    paramost cache-clear frames       delete the frame cache only (downloads are kept)
    paramost search "Barnard's Star" --fov 10 --detector D2 [--csv out.csv] [--thumbnails dir/]
                                      blind search for moving and changing sources in the field
    paramost --version

Also `python -m paramost ...` (works from a source checkout without installing).
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from . import __version__

HERE = Path(__file__).resolve().parent
APP = HERE / "app.py"
CONFIG = HERE / ".streamlit" / "config.toml"


def theme_flags():
    """[theme] of paramost/.streamlit/config.toml as Streamlit flags (--theme.base=dark ...).
    Streamlit only reads .streamlit/ in the folder it is started from, which for an installed
    app is anywhere, so the launcher passes the theme itself."""
    flags, section = [], None
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").strip()
        m = re.match(r'(\w+)\s*=\s*"([^"]*)"', line)
        if m and section == "theme":
            flags.append(f"--theme.{m.group(1)}={m.group(2)}")
    return flags


def streamlit_command(port=8501, address="localhost", browser=True):
    """The command that runs the app: python -m streamlit run <installed app.py> ..."""
    return [sys.executable, "-m", "streamlit", "run", str(APP),
            f"--server.port={port}", f"--server.address={address}",
            f"--server.headless={'false' if browser else 'true'}",
            "--browser.gatherUsageStats=false", *theme_flags()]


def _use_cache_dir(path):
    """--cache-dir: becomes SPHEREX_CACHE for this process and the app (set before spherex is
    imported, which reads it once)."""
    if path:
        os.environ["SPHEREX_CACHE"] = str(Path(path).expanduser().resolve())


def _size(path):
    total = n = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
                n += 1
            except OSError:
                pass
    return total, n


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def cache_info():
    """Print the cache folder, its size per part and the targets with downloaded images."""
    from spherex.net import CACHE_ROOT
    root = Path(CACHE_ROOT)
    print(f"cache folder: {root}")
    if not root.exists():
        print("  (empty: nothing downloaded yet)")
        return 0
    total = 0
    for part, what in (("cutouts", "images"), ("results", "saved results"), ("frames", "frame lists"),
                       ("gaia", "Gaia cones"), ("wise", "CatWISE cones")):
        size, n = _size(root / part) if (root / part).exists() else (0, 0)
        total += size
        print(f"  {part + '/':12s} {human(size):>9s}  {n} {what}")
    from spherex import framecache
    fc = framecache.info()
    total += fc["size_bytes"]
    cap = f"cap {human(fc['max_bytes'])}" if fc["max_bytes"] else "no cap"
    state = "" if fc["enabled"] else ", OFF (SPHEREX_FRAME_CACHE=0)"
    print(f"  {'frames_proc/':12s} {human(fc['size_bytes']):>9s}  {fc['entries']} aligned frames "
          f"({cap}{state}; clear with: paramost cache-clear frames)")
    print(f"  {'total':12s} {human(total):>9s}")
    try:
        from paramost.index import load_index
        targets = load_index(root)
    except Exception as e:                      # a broken index never stops cache-info
        print(f"targets: could not read the index ({type(e).__name__})")
        return 0
    if not targets:
        print("targets: none with downloaded images yet")
        return 0
    print(f"targets with downloaded images ({len(targets)}), newest first:")
    for t in targets:
        print(f"  {t['name'][:40]:40s} {human(t.get('size_bytes', 0)):>9s}  last viewed {t.get('last_viewed', '?')[:10]}")
    return 0


def cache_clear(what):
    """Delete one recomputable part of the cache. 'frames': the frame cache (frames_proc/)."""
    from spherex import framecache
    n, size = framecache.clear()
    print(f"frame cache cleared: {n} aligned frames, {human(size)} ({framecache.FRAME_DIR}). "
          "Downloaded images and saved results were kept.")
    return 0


def search(a):
    """paramost search: api.find_movers on one field, printed as a table (and optionally written)."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    if a.offline:
        os.environ["SPHEREX_DEMO"] = "1"
    from spherex import api
    from spherex.progress import Estimate
    est = Estimate()
    last = [""]

    def progress(stage, done, total):
        line = est.update(stage, done, total)["text"]
        if line != last[0]:
            print(f"\r  {line:<70}", end="", file=sys.stderr, flush=True)
            last[0] = line
    try:
        t = api.find_movers(a.target, fov=a.fov, detector=None if a.wl and not a.detector else (a.detector or "D2"),
                            wl=a.wl, days=a.days, clip=not a.no_clip, nsigma=a.sigma, method=a.method,
                            pairs=a.pairs, catalogues=not a.no_catalogues, asteroids=not a.no_asteroids,
                            progress=progress)
    except ValueError as e:
        print(f"\r{' ' * 74}\r{e}", file=sys.stderr)
        return 2
    print(f"\r{' ' * 74}\r", end="", file=sys.stderr)
    s, cuts, cat = t.meta["settings"], t.meta["cuts"], t.meta["catalogues"]
    print(f"{s['text']}: {s['detector']}, {s['fov']:g}' field, {s['visits']} visits ({', '.join(s['dates'])}; "
          f"{', '.join(s['releases'])}), clip={'on' if s['clip'] else 'off'}, {s['nsigma']:g} sigma, {s['method']}")
    removed = ", ".join(f"{k} {cuts[k]}" for k in ("low coverage", "edge", "saturated star wings", "small change"))
    print(f"residuals {cuts['residuals']}; removed: {removed}; kept {cuts['kept']}"
          + ("" if cuts["saturation_cut"] else " (no saturation cut: images not on disk)"))
    if cat.get("failed"):
        print("catalogues that failed: " + "; ".join(cat["failed"]))
    show = t["rank", "pair", "type", "ra", "dec", "significance", "pm_arcsec_yr", "label", "nearest_sep_arcsec"]
    for col, fmt in (("ra", ".5f"), ("dec", "+.5f"), ("significance", ".0f"), ("pm_arcsec_yr", ".2f"),
                     ("nearest_sep_arcsec", ".1f")):
        show[col].format = fmt
    show.pprint(max_lines=-1, max_width=-1)
    counts = ", ".join(f"{k}: {v}" for k, v in cat.get("labels", {}).items())
    print(f"{len(t)} candidates ({counts}).")
    print(t.meta["note"])
    if a.csv:
        out = t.copy()
        out.meta = {}
        out.write(a.csv, format="ascii.csv", overwrite=True)
        print(f"table: {a.csv}")
    if a.thumbnails:
        paths = api.search_thumbnails(t, a.thumbnails)
        print(f"{len(paths)} thumbnails: {a.thumbnails}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="paramost", description="Start the SPHEREx Flipbook app (SPHEREx images "
                                "from NASA's IRSA archive) or look after its cache.")
    p.add_argument("--version", action="version", version=f"paramost {__version__}")
    p.add_argument("--port", type=int, default=8501, help="port of the app (default 8501)")
    p.add_argument("--address", default="localhost", help="address to listen on; 0.0.0.0 serves other "
                   "machines (Docker). Default localhost: this computer only")
    p.add_argument("--offline", action="store_true", help="start with Offline on: only data already downloaded")
    p.add_argument("--cache-dir", help="cache folder (default: SPHEREX_CACHE, else the user cache folder)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    sub = p.add_subparsers(dest="command", metavar="command")
    info = sub.add_parser("cache-info", help="where the cache is, its size, which targets are in it")
    info.add_argument("--cache-dir", dest="sub_cache_dir", help="cache folder to look at")
    clear = sub.add_parser("cache-clear", help="delete a recomputable part of the cache "
                           "('frames': the cleaned, aligned frames; downloads are kept)")
    clear.add_argument("what", choices=["frames"], help="frames: the frame cache (frames_proc/)")
    clear.add_argument("--cache-dir", dest="sub_cache_dir", help="cache folder to clear in")
    srch = sub.add_parser("search", help="blind search of a field for moving and changing sources "
                          "(prints a table of candidates; not detections)")
    srch.add_argument("target", help="a name or coordinates, as in the app")
    srch.add_argument("--fov", type=float, default=10.0, help="field of view in arcmin, 1-10 (default 10)")
    srch.add_argument("--detector", default=None, help="D1..D6 or combinations like D5+D6 (default D2)")
    srch.add_argument("--wl", default=None, help="wavelength range in micron instead of a detector, e.g. 4.4-4.7")
    srch.add_argument("--days", type=float, default=60, help="time step: 60 per visit (default), 30, 7")
    srch.add_argument("--no-clip", action="store_true", help="plain average stacks: keeps fast movers and "
                      "flares, but also single-frame defects")
    srch.add_argument("--sigma", type=float, default=5.0, help="detection threshold in noise sigmas (default 5)")
    srch.add_argument("--method", choices=["pairs", "minus_mean"], default="pairs")
    srch.add_argument("--pairs", choices=["consecutive", "all"], default="consecutive")
    srch.add_argument("--no-catalogues", action="store_true", help="skip Gaia DR3 and CatWISE2020")
    srch.add_argument("--no-asteroids", action="store_true", help="skip SkyBoT (slow: seconds to a minute per visit)")
    srch.add_argument("--offline", dest="search_offline", action="store_true",
                      help="only images already downloaded")
    srch.add_argument("--csv", help="also write the table to this CSV file")
    srch.add_argument("--thumbnails", help="also write one PNG per candidate into this folder")
    srch.add_argument("--cache-dir", dest="sub_cache_dir", help="cache folder to use")
    a = p.parse_args(argv)
    if a.command == "search":
        a.offline = a.offline or a.search_offline

    _use_cache_dir(getattr(a, "sub_cache_dir", None) or a.cache_dir)
    if a.command == "cache-info":
        return cache_info()
    if a.command == "cache-clear":
        return cache_clear(a.what)
    if a.command == "search":
        return search(a)

    env = dict(os.environ)
    env.setdefault("MPLBACKEND", "Agg")
    if a.offline:
        env["SPHEREX_DEMO"] = "1"           # the app starts with its Offline toggle on
    print(f"paramost {__version__}: http://{'localhost' if a.address in ('localhost', '0.0.0.0') else a.address}:{a.port}"
          + ("  (offline)" if a.offline else "") + "   Ctrl+C stops it.", flush=True)
    try:
        return subprocess.call(streamlit_command(a.port, a.address, not a.no_browser), env=env)
    except KeyboardInterrupt:
        return 0
