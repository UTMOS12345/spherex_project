"""Rebuild the docs/ gallery (docs/img/gallery/<target>/) from the cache. A thin wrapper of

    paramost render --targets docs/gallery.txt --out docs/img/gallery --offline --no-timings

Nothing is downloaded: a product with an image missing from the cache fails (exit code 1) and
its old file is removed, so `git status` shows what could not be rebuilt. Other arguments are
passed on to `paramost render`, for example:

    python tools/make_gallery.py --partial          # make spectra from the cached images, marked partial
    python tools/make_gallery.py --out out/gallery  # look before replacing docs/img/gallery

The targets and their settings are in docs/gallery.txt. With unchanged inputs the files are
byte-identical, so a rebuild changes nothing in git.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                    # a source checkout without an install

from paramost.cli import main                    # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["render", "--targets", str(ROOT / "docs" / "gallery.txt"),
                           "--out", str(ROOT / "docs" / "img" / "gallery"), "--offline", "--no-timings",
                           *sys.argv[1:]]))
