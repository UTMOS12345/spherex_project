"""The `paramost` command: start the SPHEREx Flipbook app and look after its data cache.

    paramost                          open the app in the browser (live: downloads on request)
    paramost --offline                start with Offline on: only data already downloaded
    paramost --port 8502 --no-browser
    paramost --cache-dir D:\\spherex   use another cache folder (default: the user cache folder)
    paramost cache-info               where the cache is, its size, which targets are in it
    paramost cache-clear frames       delete the frame cache only (downloads are kept)
    paramost render "WISE 0855" --out wise0855/ --products video,spectrum
    paramost render --targets targets.txt --out gallery/ --offline
                                      the app's products as files (PNG, GIF, CSV, summary.json)
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
    from . import render
    rend = sub.add_parser("render", help="write the app's products to files (PNG, GIF, CSV and a JSON "
                          "summary with every warning), for one target or a list",
                          description=render.__doc__.split("\n\n")[0])
    render.add_arguments(rend)
    a = p.parse_args(argv)

    _use_cache_dir(getattr(a, "sub_cache_dir", None) or a.cache_dir)
    if a.command == "cache-info":
        return cache_info()
    if a.command == "cache-clear":
        return cache_clear(a.what)
    if a.command == "render":
        os.environ.setdefault("MPLBACKEND", "Agg")
        if a.offline or a.render_offline:
            os.environ["SPHEREX_DEMO"] = "1"
        return render.run(a)

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
