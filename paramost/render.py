"""`paramost render`: the app's products written to files, for scripts and pipelines.

    paramost render "WISE 0855" --detector D6 --fov 4 --out wise0855/ \\
        --products video,difference,overlay,light-curve,spectrum
    paramost render --targets targets.txt --out gallery/ --offline

Everything is made by spherex.api, exactly as the app makes it; this module only chooses the
calls, writes what they return, and reports. Per target it writes one file per product
(PNG or GIF; tables also as CSV) and summary.json: the settings used, the products made (with
their size and SHA-256), every warning the api returned, and the timings.

A targets file has one target per line, optionally followed by `|` and per-target options
(the same options as on the command line); `#` starts a comment:

    WISE 0855       | --detector D6 --band 4.5
    Barnard's Star  | --products video,difference
    133.795 -7.245

With --targets, each target goes into its own folder <out>/<name>/ (name: the text as a file
name, lower case, or --name). With one target on the command line, the files go into <out>/.

--offline uses only data already downloaded and fails a product clearly when any image it
needs is missing (instead of making it from the rest); --offline --partial makes it from the
images that are there and says so ("partial: k of n images") in the terminal and summary.json.
Without --offline, the number of images to download and a time estimate are printed first;
--yes is needed to go ahead unattended.

Exit codes: 0 every requested product of every target was made; 1 some were not (the summary
says which and why); 2 bad arguments or targets file; 3 downloads needed and not confirmed.
"""
import argparse
import contextlib
import hashlib
import io
import json
import re
import shlex
import sys
import time
from pathlib import Path

PRODUCTS = ("video", "difference", "overlay", "light-curve", "spectrum", "deep", "flags", "search")
DEFAULT_PRODUCTS = ("video", "difference", "overlay", "light-curve", "spectrum")
# products whose pictures are the stacked visits of api.epochs (same settings -> same stacks)
PICTURE_PRODUCTS = ("video", "difference", "overlay", "deep", "search")
FILES = {                                   # product -> the files it writes (search also: search/*.png)
    "video": ["video.gif"],
    "difference": ["difference.png"],
    "overlay": ["overlay.png"],
    "light-curve": ["light_curve.png", "light_curve.csv"],
    "spectrum": ["spectrum.png", "spectrum.csv"],
    "deep": ["deep.png"],
    "flags": ["flags.png", "flags.csv"],
    "search": ["search.csv"],
}
SUMMARY = "summary.json"
# PNG text chunks matplotlib would write: only "Software" (its version) today; PNG gets no
# creation date (PDF/SVG/PS do). None drops a key, so a rebuild on another matplotlib version
# does not change files whose pixels are the same. GIFs (Pillow) carry no metadata.
PNG_METADATA = {"Software": None}
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_NOT_CONFIRMED = 0, 1, 2, 3


class UsageError(Exception):
    """Bad arguments or targets file (exit code 2)."""


class _Parser(argparse.ArgumentParser):
    """An argument parser for one line of a targets file: errors raise instead of exiting."""

    def error(self, message):
        raise UsageError(message)


# ------------------------------------------------------------------ options
def add_target_options(p, suppress=False):
    """Options that can differ per target (command line and targets-file lines)."""
    d = (lambda v: argparse.SUPPRESS) if suppress else (lambda v: v)
    p.add_argument("--products", default=d(None),
                   help="comma-separated: " + ", ".join(PRODUCTS) + ", or 'all' "
                   f"(default: {','.join(DEFAULT_PRODUCTS)})")
    p.add_argument("--detector", default=d(None), help="D1..D6 or combinations like D5+D6 "
                   "(default: the target's default, as in the app)")
    p.add_argument("--wl", default=d(None), help="wavelength range in micron instead of a detector, e.g. 4.4-4.7 "
                   "(video, difference, deep, search)")
    p.add_argument("--fov", type=float, default=d(4.0), help="field of view in arcmin, 1-10 (default 4)")
    p.add_argument("--days", type=float, default=d(60), help="time step: 60 per visit (default), 30, 7, 0 every frame")
    p.add_argument("--no-clip", action="store_true", default=d(False),
                   help="plain average stacks (keeps fast movers and flares, and single-frame defects)")
    p.add_argument("--visit", type=int, default=d(-1), help="picture shown by overlay and flags, visit of the "
                   "spectrum: 0 = first, -1 = latest (default)")
    p.add_argument("--band", type=float, default=d(None), help="light-curve wavelength in micron "
                   "(default: the target's default)")
    p.add_argument("--tol", type=float, default=d(None), help="light-curve tolerance in micron (default: the target's)")
    p.add_argument("--fps", type=int, default=d(3), help="video: pictures per second (default 3)")
    p.add_argument("--name", default=d(None), help="folder name for this target with --targets")


def add_arguments(p):
    """The `render` subcommand's arguments."""
    p.add_argument("target", nargs="?", help="a name or coordinates, as in the app")
    p.add_argument("--targets", help="a file with one target per line (and optional options after '|')")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--offline", dest="render_offline", action="store_true",
                   help="only data already downloaded; a product missing any image fails")
    p.add_argument("--partial", action="store_true", help="with --offline: make a product from the cached "
                   "images even when some are missing, marked partial in the summary")
    p.add_argument("--yes", "-y", action="store_true", help="download what is needed without asking")
    p.add_argument("--style", choices=["dark", "light"], default="dark", help="figure colours (default dark, as the app)")
    p.add_argument("--dpi", type=float, default=None, help="resolution of the PNG files (default: the figure's, "
                   "110 as in the app)")
    p.add_argument("--no-timings", action="store_true", help="leave the timings out of summary.json, so that a "
                   "rebuild with unchanged inputs gives byte-identical files")
    add_target_options(p)
    p.add_argument("--cache-dir", dest="sub_cache_dir", help="cache folder to use")


def parse_products(text):
    """'video,spectrum' / 'all' -> tuple of product names in PRODUCTS order. 'all' is every
    product this installation can make (search needs spherex.api.find_movers)."""
    if not text:
        return DEFAULT_PRODUCTS
    wanted = [w.strip().lower().replace("_", "-") for w in text.split(",") if w.strip()]
    if "all" in wanted:
        return tuple(p for p in PRODUCTS if p != "search" or _search_available())
    unknown = [w for w in wanted if w not in PRODUCTS]
    if unknown:
        raise UsageError(f"unknown product {', '.join(unknown)}; choose from {', '.join(PRODUCTS)} or all")
    return tuple(p for p in PRODUCTS if p in wanted)


def _search_available():
    from spherex import api
    return hasattr(api, "find_movers")


def slug(text):
    """Folder name of a target: the text as a file name, lower case ("Barnard's Star" -> barnard_s_star)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower() or "target"


def read_targets(path, base):
    """Targets file -> [(text, options)], each options a copy of `base` with that line's options."""
    p = _Parser(prog="targets file", add_help=False)
    add_target_options(p, suppress=True)
    jobs = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise UsageError(f"cannot read the targets file: {e}")
    for n, line in enumerate(lines, 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        text, _, opts = line.partition("|")
        text = text.strip()
        if not text:
            raise UsageError(f"{path}, line {n}: no target before '|'")
        try:
            extra = vars(p.parse_args(shlex.split(opts)))
        except (UsageError, ValueError) as e:
            raise UsageError(f"{path}, line {n}: {e}")
        jobs.append((text, argparse.Namespace(**{**vars(base), **extra})))
    if not jobs:
        raise UsageError(f"{path}: no targets")
    return jobs


# ------------------------------------------------------------------ terminal progress
class Progress:
    """The api's progress callback, shown on the terminal (stderr): one updating line on a
    terminal, the start of each stage otherwise (logs)."""
    WIDTH = 78

    def __init__(self, stream=None):
        self.stream = stream or sys.stderr
        self.tty = self.stream.isatty()
        self.label, self.last, self.est = "", None, None

    def start(self, label):
        from spherex.progress import Estimate
        self.label, self.last, self.est = label, None, Estimate()

    def __call__(self, stage, done, total):
        info = self.est.update(stage, done, total)
        if self.tty:
            line = f"    {self.label}: {info['text']}"[:self.WIDTH]
            print(f"\r{line:<{self.WIDTH}}", end="", file=self.stream, flush=True)
        elif stage != self.last:
            print(f"    {self.label}: {stage}", file=self.stream, flush=True)
        self.last = stage

    def clear(self):
        if self.tty:
            print(f"\r{' ' * self.WIDTH}\r", end="", file=self.stream, flush=True)


# ------------------------------------------------------------------ one target
class Target:
    """One target's settings, plan (which products, which images are missing) and results."""

    def __init__(self, text, o, folder):
        self.text, self.o, self.folder = text, o, Path(folder)
        self.products = parse_products(o.products)
        self.info = None                 # api.resolve
        self.error = None                # the target could not be started at all
        self.blocked = {}                # product -> reason it will not be run
        self.partial = {}                # product -> note: made offline from only some of its images
        self.missing = {}                # count key -> (missing, total)
        self.results = {}                # product -> dict for summary.json
        self.seconds = {}

    # settings, filled from api.defaults where not given
    def settings(self):
        o = self.o
        return {"detector": self.detector, "wl": o.wl, "fov": o.fov, "days": o.days, "clip": not o.no_clip,
                "visit": o.visit, "band": self.band, "tol": self.tol, "fps": o.fps}

    def resolve(self, api):
        self.info = api.resolve(self.text)
        d = api.defaults(self.text)
        o = self.o
        self.detector = None if (o.wl and not o.detector) else (o.detector or d["detector"])
        self.band = o.band if o.band is not None else d["band"]
        self.tol = o.tol if o.tol is not None else d["tol"]

    def calls(self, api):
        """product -> (count key, api function, args, kwargs) of the call whose images it needs."""
        o, clip = self.o, not self.o.no_clip
        stacks = (api.epochs, (self.text,), dict(detector=self.detector, fov=o.fov, wl=o.wl, days=o.days, clip=clip))
        over = (api.epochs, (self.text,), dict(detector=self.detector or "D2", fov=o.fov, wl=None, days=o.days,
                                               clip=True))
        return {
            "video": stacks, "difference": stacks, "deep": stacks, "search": stacks, "overlay": over,
            "light-curve": (api.light_curve_figure, (self.text,), dict(band=self.band, tol=self.tol)),
            "spectrum": (api.spectrum_figure, (self.text,), dict(visit=o.visit)),
        }

    def paths(self, product):
        return [self.folder / f for f in FILES[product]]


def _key(call):
    fn, args, kwargs = call
    return (fn.__name__, args, tuple(sorted(kwargs.items())))


def count_missing(api, t, offline, partial=False):
    """Fill t.missing: per distinct api call of t's products, (images missing, images used).
    The count reads the cache only (api.count_downloads stops before the first download);
    offline it runs with demo mode off just for the count, after checking that the frame
    list is cached, so nothing is searched or downloaded."""
    calls = t.calls(api)
    was = api.demo_mode()
    if offline:
        if api.target_files(t.text)["frame_list"] is None:
            raise ValueError(f"'{t.text}' has no frame list in the cache (offline: the archive is not searched). "
                             "Run once without --offline to search and download it.")
        api.set_demo_mode(False)
    try:
        for product in t.products:
            if product not in calls:
                continue
            call = calls[product]
            key = _key(call)
            if key not in t.missing:
                fn, args, kwargs = call
                try:
                    c = api.count_downloads(fn, *args, **kwargs)
                    t.missing[key] = (c["missing"], c["total"])
                except (ValueError, OSError) as e:
                    t.missing[key] = e
            m = t.missing[key]
            if isinstance(m, Exception):
                t.blocked[product] = _message(m)
            elif offline and m[0] and partial:
                t.partial[product] = (f"partial: made from the {m[1] - m[0]} of {m[1]} images in the cache; the "
                                      f"other {m[0]} are not downloaded (run without --offline to complete it)")
            elif offline and m[0]:
                t.blocked[product] = (f"{m[0]} of the {m[1]} images it needs are not in the cache (offline: nothing "
                                      "is downloaded). Run without --offline to download them, or add --partial.")
    finally:
        api.set_demo_mode(was)


def _message(e):
    return str(e) if isinstance(e, ValueError) else f"{type(e).__name__}: {e}"


# ------------------------------------------------------------------ the products
def _picture_warnings(api, t, kind):
    """The few-frames and data-release notes of the pictures a product shows (api.epochs)."""
    o = t.o
    if kind == "overlay":
        rows = api.epochs(t.text, detector=t.detector or "D2", fov=o.fov, days=o.days)
    else:
        rows = api.epochs(t.text, detector=t.detector, fov=o.fov, wl=o.wl, days=o.days, clip=not o.no_clip)
    idx = list(range(len(rows)))
    if kind == "difference":
        idx = sorted({idx[0], idx[-1]}) if idx else []
    elif kind in ("overlay",):
        idx = [idx[o.visit]] if idx else []
    sel = [rows[i] for i in idx]
    out = []
    few = [r for r in sel if r["few_frames"]]
    if few:
        out.append(f"{api.FEW_FRAMES_NOTE}: " + "; ".join(
            f"picture {int(r['index'])} ({r['date']}): {int(r['n_min'])} frames under the centre" for r in few))
    releases = sorted({x.strip() for r in sel for x in str(r["releases"]).split(",") if x.strip()})
    if len(releases) > 1:
        out.append(f"pictures from more than one data release ({', '.join(releases)}): a change between "
                   "releases may be calibration, not a real change")
    return out


def make_product(api, t, product, progress):
    """Run one product -> (files {name: figure | bytes | table}, warnings [str], notes dict).
    Raises ValueError / OSError when it cannot be made."""
    o, clip = t.o, not t.o.no_clip
    pic = dict(detector=t.detector, fov=o.fov, wl=o.wl, days=o.days, clip=clip)
    if product == "video":
        gif = api.flipbook(t.text, fps=o.fps, progress=progress, **pic)
        return {"video.gif": gif}, _picture_warnings(api, t, product), {}
    if product == "difference":                       # the latest picture minus the first
        fig = api.picture(t.text, "pair", a=-1, b=0, progress=progress, **pic)
        return {"difference.png": fig}, _picture_warnings(api, t, product), {}
    if product == "deep":
        fig = api.picture(t.text, "deep", progress=progress, **pic)
        return {"deep.png": fig}, _picture_warnings(api, t, product), {}
    if product == "overlay":
        fig, notes = api.overlay_figure(t.text, detector=t.detector or "D2", fov=o.fov, visit=o.visit, days=o.days,
                                        progress=progress)
        if notes.get("failed"):
            import matplotlib.pyplot as plt
            plt.close(fig)
            raise OSError("catalogues could not be reached: " + "; ".join(notes["failed"]))
        return {"overlay.png": fig}, _picture_warnings(api, t, product), notes
    if product == "light-curve":
        fig, table = api.light_curve_figure(t.text, band=t.band, tol=t.tol, progress=progress)
        return {"light_curve.png": fig, "light_curve.csv": table}, _table_warnings(table), {}
    if product == "spectrum":
        fig, table = api.spectrum_figure(t.text, visit=o.visit, progress=progress)
        return {"spectrum.png": fig, "spectrum.csv": table}, _table_warnings(table), {}
    if product == "flags":
        fig, table = api.flags_figure(t.text, detector=(t.detector or "D2").split("+")[0], visit=o.visit)
        return {"flags.png": fig, "flags.csv": table}, [], {}
    if product == "search":
        if not _search_available():
            raise ValueError("this version of spherex has no blind search (spherex.api.find_movers)")
        table = api.find_movers(t.text, progress=progress, **pic)
        meta = dict(table.meta)
        warnings = list(_picture_warnings(api, t, product))
        failed = meta.get("catalogues", {}).get("failed")
        if failed:
            warnings.append("catalogues that failed: " + "; ".join(failed))
        if not meta.get("settings", {}).get("saturation_cut", True):
            warnings.append("no saturation cut: the images were not all on disk")
        folder = t.folder / "search"
        for old in folder.glob("*.png") if folder.is_dir() else ():
            old.unlink()
        thumbs = api.search_thumbnails(table, folder)
        notes = {k: v for k, v in meta.items() if k != "rejected"}
        notes["thumbnails"] = [str(Path(p).relative_to(t.folder)) for p in thumbs]
        return {"search.csv": table}, warnings, notes
    raise ValueError(f"unknown product {product}")


@contextlib.contextmanager
def library_output(stream=None):
    """What the library prints while a product is made, tidied: its per-frame "skipped ..."
    lines (frames not in the cache offline) become one count; every other line is passed on."""
    stream = stream or sys.stdout
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            yield
    finally:
        lines = [x.strip() for x in buf.getvalue().splitlines() if x.strip()]
        skipped = sum(1 for x in lines if x.startswith("skipped "))
        for x in lines:
            if not x.startswith("skipped "):
                print(f"         {x}", file=stream)
        if skipped:
            print(f"         {skipped} frame{'s' if skipped != 1 else ''} skipped (not in the cache)", file=stream)


def _table_warnings(table):
    w = table.meta.get("warning")
    return [w] if w else []


def write_file(path, obj, dpi=None):
    """Write a figure (PNG; closed afterwards), GIF bytes, or a table (CSV, without its meta).
    Nothing that changes between runs is written: no timestamps or versions in the PNG, no meta
    in the CSV, so unchanged inputs give byte-identical files."""
    import matplotlib.pyplot as plt
    from astropy.table import Table
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, bytes):
        path.write_bytes(obj)
    elif isinstance(obj, Table):
        out = obj.copy(copy_data=False)
        out.meta = {}
        out.write(path, format="ascii.csv", overwrite=True)
    else:
        try:
            obj.savefig(path, format="png", dpi=dpi or "figure", bbox_inches="tight", metadata=PNG_METADATA)
        finally:
            plt.close(obj)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plain(x):
    """A value made fit for JSON (numpy numbers and arrays, tuples, NaN -> None)."""
    import numpy as np
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return _plain(x.tolist())
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not np.isfinite(x):
        return None
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)


def run_target(api, t, progress, timings=True, dpi=None):
    """Make t's products (those not blocked), write them and summary.json -> True if all were made."""
    t0 = time.perf_counter()
    t.folder.mkdir(parents=True, exist_ok=True)
    for product in t.products:
        entry = {"files": {}, "warnings": []}
        start = time.perf_counter()
        reason = t.error or t.blocked.get(product)
        if reason is None:
            progress.start(product)
            try:
                with library_output():
                    files, warnings, notes = make_product(api, t, product, progress)
                for name, obj in files.items():
                    write_file(t.folder / name, obj, dpi)
                if product == "search":
                    files.update({p: None for p in notes.get("thumbnails", [])})
                for name in files:
                    p = t.folder / name
                    entry["files"][name] = {"bytes": p.stat().st_size, "sha256": _digest(p)}
                if product in t.partial:
                    warnings = [t.partial[product]] + warnings
                    entry["partial"] = True
                entry.update(status="made", warnings=warnings)
                if notes:
                    entry["notes"] = _plain(notes)
            except Exception as e:                 # reported, never hidden
                reason = _message(e)
            finally:
                progress.clear()
        if reason is not None:
            for p in t.paths(product):             # never leave an old file that looks current
                p.unlink(missing_ok=True)
            entry.update(status="failed", error=reason)
        t.seconds[product] = round(time.perf_counter() - start, 2)
        t.results[product] = entry
        made = entry["status"] == "made"
        what = ", ".join(entry["files"]) if made else entry["error"]
        state = ("partly" if entry.get("partial") else "made  ") if made else "FAILED"
        print(f"  {state} {product:12s} {what}"
              + (f"  ({t.seconds[product]:.1f} s)" if made else ""), flush=True)
        for w in entry["warnings"]:
            print(f"         warning: {w}", flush=True)
    write_summary(api, t, time.perf_counter() - t0, timings)
    return all(r["status"] == "made" for r in t.results.values())


def write_summary(api, t, seconds, timings):
    from spherex import __version__ as spherex_version
    from paramost import __version__ as paramost_version
    info = t.info or {}
    summary = {
        "target": t.text,
        "resolved": _plain({k: info.get(k) for k in ("name", "ra", "dec", "ra_hms", "dec_dms", "pm_ra", "pm_dec")})
        if t.info else None,
        "settings": _plain(t.settings()) if t.info else None,
        "offline": api.demo_mode(),
        "versions": {"spherex": spherex_version, "paramost": paramost_version},
        "products_requested": list(t.products),
        "products_made": [p for p, r in t.results.items() if r["status"] == "made"],
        "products_partial": [p for p, r in t.results.items() if r.get("partial")],
        "products_failed": {p: r["error"] for p, r in t.results.items() if r["status"] != "made"},
        # images not in the cache per api call. Not the totals: a saved result answers the
        # count with 0 of 0, so they would differ between a cold and a warm run.
        "images_missing": [{"call": k[0], "missing": v[0]} for k, v in t.missing.items()
                           if not isinstance(v, Exception)],
        "warnings": [{"product": p, "warning": w} for p, r in t.results.items() for w in r["warnings"]],
        "products": t.results,
    }
    if t.error:
        summary["error"] = t.error
    if timings:
        summary["timings_seconds"] = {"total": round(seconds, 2), **t.seconds}
    (t.folder / SUMMARY).write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                    encoding="utf-8")


# ------------------------------------------------------------------ the command
def jobs_from_args(a):
    if bool(a.target) == bool(a.targets):
        raise UsageError("give one target, or --targets FILE (not both)")
    if a.target:
        return [(a.target, argparse.Namespace(**vars(a)), Path(a.out))]
    jobs = read_targets(a.targets, a)
    out, seen = [], set()
    for text, o in jobs:
        folder = Path(a.out) / (o.name or slug(text))
        if folder in seen:
            raise UsageError(f"two targets would share the folder {folder}: give one of them --name")
        seen.add(folder)
        out.append((text, o, folder))
    return out


def confirm(n, stream_in=None):
    """Ask on the terminal whether to download n images. No terminal: False (needs --yes)."""
    stream_in = stream_in or sys.stdin
    if not stream_in.isatty():
        return False
    try:
        return input("Download them now? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def run(a):
    """paramost render -> exit code."""
    offline = bool(getattr(a, "offline", False) or a.render_offline)
    try:
        if a.partial and not offline:
            raise UsageError("--partial needs --offline (without it, missing images are downloaded)")
        jobs = jobs_from_args(a)
        for _, o, _ in jobs:
            parse_products(o.products)
    except UsageError as e:
        print(f"paramost render: {e}", file=sys.stderr)
        return EXIT_USAGE

    from spherex import api, set_style
    from paramost.estimate import download_time
    api.set_demo_mode(offline)
    set_style(dark=a.style == "dark")
    targets = [Target(text, o, folder) for text, o, folder in jobs]

    # 1. plan: resolve every target, count what is missing
    print(f"paramost render: {len(targets)} target{'s' if len(targets) != 1 else ''}"
          + (" (offline: cached data only)" if offline else ""), flush=True)
    for t in targets:
        try:
            t.resolve(api)
            count_missing(api, t, offline, a.partial)
        except Exception as e:
            t.error = _message(e)
    if not offline:
        n = sum(v[0] for t in targets for v in t.missing.values() if not isinstance(v, Exception))
        flags = sum(1 for t in targets if "flags" in t.products and not t.error)
        if n or flags:
            print(f"{n} images to download" + (" (at most: products can share images)" if n else "")
                  + (f", plus up to {flags} for flags" if flags else "")
                  + f": {download_time(n + flags)}. IRSA's speed varies.", flush=True)
            if n and not a.yes and not confirm(n):
                print("Not downloading: rerun with --yes to download without asking, or with --offline "
                      "to use only the cache.", file=sys.stderr)
                return EXIT_NOT_CONFIRMED
        else:
            print("Nothing to download: every image needed is in the cache.", flush=True)

    # 2. make the products, one target after another (each uses the worker pool for its frames)
    progress = Progress()
    t0 = time.perf_counter()
    for i, t in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {t.text} -> {t.folder}", flush=True)
        if t.error:
            print(f"  FAILED {t.error}", flush=True)
        run_target(api, t, progress, timings=not a.no_timings, dpi=a.dpi)

    # 3. what failed and why
    failed = [(t, p, r["error"]) for t in targets for p, r in t.results.items() if r["status"] != "made"]
    made = sum(1 for t in targets for r in t.results.values() if r["status"] == "made")
    partly = sum(1 for t in targets for r in t.results.values() if r.get("partial"))
    print(f"done in {time.perf_counter() - t0:.1f} s: {made} of {made + len(failed)} products made"
          + (f", {partly} of them partial (from only the cached images)" if partly else "") + ".", flush=True)
    if failed:
        print("Not made:", flush=True)
        for t, p, why in failed:
            print(f"  {t.text}: {p}: {why}", flush=True)
        return EXIT_FAILED
    return EXIT_OK
