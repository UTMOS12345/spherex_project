"""The `paramost` command: starts the SPHEREx Flipbook app (paramost/app.py) with its theme."""
import os
import re
import subprocess
import sys
from pathlib import Path

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


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="paramost", description="Start the SPHEREx Flipbook app.")
    p.add_argument("--port", type=int, default=8501)
    p.add_argument("--address", default="localhost", help="0.0.0.0 to serve other machines (Docker)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    a = p.parse_args(argv)
    env = dict(os.environ)
    env.setdefault("MPLBACKEND", "Agg")
    return subprocess.call(streamlit_command(a.port, a.address, not a.no_browser), env=env)
