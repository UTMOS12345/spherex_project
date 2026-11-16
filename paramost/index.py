"""The index of the user's targets: <cache>/targets.json.

One entry per target the user has viewed, so the start screen can show "Your targets"
without scanning every FITS file:
    key          the target's cache name in file-name form (as cache/frames/<key>.ecsv)
    name         what to show (the name as typed, or coordinates)
    text         what to put in the search box to open it again
    ra, dec      catalogue position (degrees)
    settings     the view settings it was last seen with (the link parameters)
    last_viewed  ISO date and time
    n_images     downloaded images; entries with 0 are not shown
    size_bytes   everything the cache holds for it (images, frame list, results, cones)

The file is written atomically. If it is missing or cannot be read, it is rebuilt from the
cache (frame lists and image names); a rebuilt entry has no settings, and a target that was
typed as coordinates comes back under the coordinates of its images.
"""
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

INDEX_NAME = "targets.json"
VERSION = 1
_lock = threading.Lock()


def index_path(root):
    return Path(root) / INDEX_NAME


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="microseconds")   # orders views within a second


def _write(root, entries):
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.part")
    part.write_text(json.dumps({"version": VERSION, "targets": entries}, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(part, path)


def _valid(data):
    return (isinstance(data, dict) and data.get("version") == VERSION and isinstance(data.get("targets"), dict)
            and all(isinstance(v, dict) and "name" in v and "text" in v for v in data["targets"].values()))


def read(root):
    """All entries: key -> entry. Rebuilds the file from the cache when it is missing or broken."""
    path = index_path(root)
    with _lock:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if _valid(data):
                return data["targets"]
        except (OSError, ValueError):
            pass
        entries = rebuild(root)
        try:
            _write(root, entries)
        except OSError:
            pass
        return entries


def load_index(root):
    """Targets with downloaded images, most recently viewed first -> list of entries."""
    entries = [dict(v, key=k) for k, v in read(root).items() if v.get("n_images", 0) > 0]
    return sorted(entries, key=lambda e: e.get("last_viewed", ""), reverse=True)


def record(root, key, **fields):
    """Add or update one target (fields: name, text, ra, dec, settings, n_images, size_bytes);
    last_viewed becomes now."""
    entries = read(root)
    with _lock:
        entry = entries.get(key, {})
        entry.update(fields, last_viewed=_now())
        entries[key] = entry
        _write(root, entries)
    return entry


def drop(root, key):
    entries = read(root)
    with _lock:
        if entries.pop(key, None) is not None:
            _write(root, entries)


def _key_positions(key):
    """Positions a frame-list name made from typed coordinates can stand for: the name keeps
    the digits but not the sign of the declination, so both signs -> [(ra, dec), ...] degrees."""
    m = re.fullmatch(r"(\d+)h(\d+)m(\d+(?:_\d+)?)s_(\d+)d(\d+)m(\d+(?:_\d+)?)s", key)
    if m:
        h, mi, se, d, dm, ds = (float(g.replace("_", ".")) for g in m.groups())
        ra, dec = 15 * (h + mi / 60 + se / 3600), d + dm / 60 + ds / 3600
        return [(ra, dec), (ra, -dec)]
    parts = key.split("_")
    if len(parts) in (2, 4) and all(p.isdigit() for p in parts):
        ra, dec = (float(".".join(parts[:2])), float(".".join(parts[2:]))) if len(parts) == 4 else map(float, parts)
        return [(ra, dec), (ra, -dec)]
    return []


def rebuild(root):
    """Entries from the cache alone: one per frame list that has downloaded images. A named
    target counts the images at its own position on each date (spherex.cachefiles); a target
    typed as coordinates (no proper motion, so one centre for all its images) counts the images
    that share the most common centre among its frames, when that centre is the position in
    the frame list's name; anything less certain is left out (it shows again once viewed)."""
    from collections import Counter
    from astropy.table import Table
    from spherex.cachefiles import CUTOUT_RE, _size, target_files
    from spherex.targets import DISPLAY, parse_target
    from spherex.net import CACHE_ROOT
    root = Path(root)
    if root.resolve() != Path(CACHE_ROOT).resolve():
        return {}                  # target matching reads the active cache (SPHEREX_CACHE) only
    frames_dir, cutouts = root / "frames", root / "cutouts"
    if not frames_dir.is_dir():
        return {}
    by_stem = {}
    if cutouts.is_dir():
        for p in cutouts.iterdir():
            m = CUTOUT_RE.match(p.name)
            if m:
                by_stem.setdefault(m["stem"], []).append((m["ra"], m["dec"], p))
    known = {re.sub(r"[^A-Za-z0-9]+", "_", n).strip("_"): n for n in DISPLAY.values()}
    entries = {}
    for table in sorted(frames_dir.glob("*.ecsv")):
        key = table.stem
        if key in known:
            try:
                target = parse_target(known[key])          # a catalogue target: no network
                files = target_files(known[key], target)
            except Exception:
                continue
            images, size = files["images"], files["size_bytes"]
            ra, dec, text = float(target.ra.deg), float(target.dec.deg), known[key]
        else:
            try:
                urls = Table.read(table)["access_url"]
            except Exception:
                continue
            found = [f for u in urls for f in by_stem.get(str(u).rsplit("/", 1)[-1].removesuffix(".fits"), ())]
            common = Counter((r, d) for r, d, _ in found).most_common(1)
            if not common or common[0][1] < 2:             # no shared centre: not this target's images
                continue
            (r, d), _ = common[0]
            # only if the name's coordinates agree: shared frames also hold other targets' images
            if not any(abs(float(r) - ra0) < 0.02 and abs(float(d) - dec0) < 0.02 for ra0, dec0 in _key_positions(key)):
                continue
            images = [p for rr, dd, p in found if (rr, dd) == (r, d)]
            size = _size(images + [table])
            ra, dec = float(r), float(d)
            text = f"{ra:.5f} {dec:+.5f}"
        if not images:
            continue
        newest = max(p.stat().st_mtime for p in images)
        entries[key] = {"name": text, "text": text, "ra": ra, "dec": dec, "settings": {},
                        "n_images": len(images), "size_bytes": size,
                        "last_viewed": datetime.fromtimestamp(newest, timezone.utc).astimezone().isoformat(timespec="seconds")}
    return entries
