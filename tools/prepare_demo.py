"""Prepare the demo: download what the five test targets need and save every product in
demo/<target>/ (SPHEREX_DEMO_DIR). A thin wrapper of

    paramost render --targets demo/targets.txt --out demo --products all --yes

with demo/targets.txt listing the five targets (spherex.api.DEMO_DEFAULTS). The images go into
the cache, so the app then shows these targets offline.

    python tools/prepare_demo.py                     # all five targets
    python tools/prepare_demo.py --only "WISE 0855"  # one target
    python tools/prepare_demo.py --refresh           # search IRSA again first (new data releases)

Safe to stop (Ctrl+C) and run again: finished downloads are kept. A failed product never stops
the rest; demo/<target>/summary.json says what was made, with every warning. Other arguments
are passed on to `paramost render` (e.g. --offline to rebuild from the cache only).
The extra products of tools/explore.py are no longer made here: run it on its own.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                    # a source checkout without an install

from paramost.cli import main                    # noqa: E402
from spherex.api import DEMO_DEFAULTS            # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--only", help="just this target")
    p.add_argument("--skip-explore", action="store_true", help=argparse.SUPPRESS)   # kept for old scripts
    a, rest = p.parse_known_args()
    names = [k for k in DEMO_DEFAULTS if not a.only or k.lower() == a.only.lower()]
    if not names:
        raise SystemExit(f"unknown target; choose from {list(DEMO_DEFAULTS)}")
    out = Path(os.environ.get("SPHEREX_DEMO_DIR", "demo"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "targets.txt").write_text("".join(f"{n}\n" for n in names), encoding="utf-8")
    raise SystemExit(main(["render", "--targets", str(out / "targets.txt"), "--out", str(out),
                           "--products", "all", "--yes", *rest]))
