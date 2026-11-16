"""Remove the PSF layers from old cutouts, writing slimmer copies to a NEW folder.

    python tools/strip_psf.py COPY_OF_CUTOUTS OUTPUT_FOLDER
    python tools/strip_psf.py cache_copy/cutouts slim/cutouts --dry-run   # sizes only

Cutouts downloaded before the PSF layer was dropped on download keep a ~4-5 MB PSF cube
(PSF or EPSF) that nothing in this project uses. This script reads every *.fits file in the
input folder and writes it to the output folder under the same name: without the PSF layers,
or copied unchanged when it has none. Each output is checked: it must open, and its IMAGE,
FLAGS and VARIANCE layers must be byte-identical to the input's (data and header). A file
that fails the check is not kept. The input folder is only ever read.

Run it on a COPY of a cache folder, then swap the folders yourself once you are happy:
the script refuses to write into the input folder, into a folder inside it, or into the
project's own cache/ (or SPHEREX_CACHE).
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))   # repo root, so tools/ can import spherex
import argparse
import os
import shutil

from astropy.io import fits

DROP_LAYERS = ("PSF", "EPSF")
CHECKED_LAYERS = ("IMAGE", "FLAGS", "VARIANCE")


def _real_cache():
    """The project's cache folder (what spherex.net uses), without importing astropy-heavy spherex."""
    root = pathlib.Path(__file__).resolve().parent.parent
    return pathlib.Path(os.environ.get("SPHEREX_CACHE") or root / "cache").resolve()


def _inside(path, folder):
    return path == folder or folder in path.parents


def strip_one(src, dst):
    """Write src without its PSF layers to dst (via a temporary name). Returns True if a layer
    was removed, False if the file was copied unchanged."""
    part = dst.with_name(f".{dst.name}.part")
    try:
        with fits.open(src, memmap=False) as h:
            names = [hdu.name for hdu in h]
            if not any(n in DROP_LAYERS for n in names):
                shutil.copyfile(src, part)
                removed = False
            else:
                fits.HDUList([hdu.copy() for hdu in h if hdu.name not in DROP_LAYERS]).writeto(part)
                removed = True
        os.replace(part, dst)
    finally:
        if part.exists():
            part.unlink()
    return removed


def check_one(src, dst):
    """'' if dst opens and its IMAGE/FLAGS/VARIANCE match src byte for byte, else the problem."""
    try:
        with fits.open(src, memmap=False) as a, fits.open(dst, memmap=False) as b:
            for name in CHECKED_LAYERS:
                if name not in a:
                    continue
                if name not in b:
                    return f"{name} missing"
                if a[name].data.tobytes() != b[name].data.tobytes():
                    return f"{name} data differ"
                if a[name].header.tostring() != b[name].header.tostring():
                    return f"{name} header differs"
            left = [h.name for h in b if h.name in DROP_LAYERS]
            if left:
                return f"still has {', '.join(left)}"
    except Exception as e:
        return f"does not open: {type(e).__name__}: {str(e)[:80]}"
    return ""


def mb(n):
    return f"{n / 1024 ** 2:,.1f} MB"


def main():
    p = argparse.ArgumentParser(description="Copy cutouts without their PSF layers into a new folder "
                                            "(works on a copy; never changes the input folder).")
    p.add_argument("input", type=pathlib.Path, help="folder with *.fits cutouts (a copy of cache/cutouts)")
    p.add_argument("output", type=pathlib.Path, help="new folder for the slimmer files (created if missing)")
    p.add_argument("--dry-run", action="store_true", help="only count files and sizes; write nothing")
    a = p.parse_args()

    src_dir, dst_dir = a.input.resolve(), a.output.resolve()
    if not src_dir.is_dir():
        p.error(f"{src_dir} is not a folder")
    if _inside(dst_dir, src_dir) or _inside(src_dir, dst_dir):
        p.error("the output folder must be separate from the input folder")
    cache = _real_cache()
    for folder in (src_dir, dst_dir):
        if _inside(folder, cache):
            p.error(f"{folder} is inside the project's cache ({cache}); copy the cutouts elsewhere first")

    files = sorted(src_dir.glob("*.fits"))
    before = sum(f.stat().st_size for f in files)
    print(f"{len(files)} files, {mb(before)} in {src_dir}")
    if a.dry_run:
        with_psf = 0
        for f in files:
            with fits.open(f, memmap=False) as h:
                with_psf += any(hdu.name in DROP_LAYERS for hdu in h)
        print(f"{with_psf} of them have a PSF layer (dry run: nothing written)")
        return 0

    dst_dir.mkdir(parents=True, exist_ok=True)
    stripped = copied = 0
    failed = []
    after = 0
    for i, f in enumerate(files, 1):
        out = dst_dir / f.name
        try:
            removed = strip_one(f, out)
        except Exception as e:
            failed.append((f.name, f"cannot read: {type(e).__name__}: {str(e)[:80]}"))
            continue
        problem = check_one(f, out)
        if problem:
            out.unlink(missing_ok=True)
            failed.append((f.name, problem))
            continue
        stripped += removed
        copied += not removed
        after += out.stat().st_size
        if i % 50 == 0 or i == len(files):
            print(f"  {i}/{len(files)}")

    kept = stripped + copied
    print(f"\n{stripped} stripped, {copied} copied unchanged (no PSF), {len(failed)} failed")
    for name, problem in failed:
        print(f"  FAILED {name}: {problem}")
    ok_before = sum((src_dir / n).stat().st_size for n in (f.name for f in files)
                    if n not in {x for x, _ in failed})
    if kept:
        print(f"size of the {kept} checked files: {mb(ok_before)} -> {mb(after)} "
              f"({100 * (1 - after / ok_before):.0f}% smaller)")
    print(f"IMAGE, FLAGS and VARIANCE byte-identical in all {kept} outputs; input folder untouched.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
