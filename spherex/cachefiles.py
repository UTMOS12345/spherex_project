"""Which files in the cache belong to one target, and removing them.

A target's files: its cutouts (cache/cutouts), its frame list (cache/frames/<name>.ecsv), its
saved results (cache/results/<name>/) and the Gaia / CatWISE cones around it (cache/gaia,
cache/wise). A cutout belongs to the target when its frame is in the target's frame list AND
its centre is where the target was on that frame's date (the file name holds both), so a
nearby target that shares frames keeps its own cutouts. A cone is a small catalogue query
(re-downloaded when needed), removed when its centre is within CONE_MATCH_DEG of the target.
"""
import re
import shutil
from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time
import astropy.units as u

from .download import CACHE_DIR
from .frames import table_path
from .net import CACHE_ROOT
from . import results
from .targets import at_time, target_name

CUTOUT_RE = re.compile(r"^(?P<stem>.+)__(?P<ra>-?[0-9.]+)_(?P<dec>[+-][0-9.]+)_(?P<size>[0-9.]+)\.fits$")
CONE_RE = re.compile(r"^(?:gaia|catwise)_(?P<ra>-?[0-9.]+)_(?P<dec>[+-]?[0-9.]+)_(?P<r>[0-9.]+)\.ecsv$")
CENTRE_TOL_DEG = 2e-5      # names round the centre to 1e-5 deg
CONE_MATCH_DEG = 0.1


def _cutout_index():
    """Every cutout in the cache: frame stem -> [(ra, dec, path)]. One folder listing."""
    index = {}
    if not CACHE_DIR.is_dir():
        return index
    for p in CACHE_DIR.iterdir():
        m = CUTOUT_RE.match(p.name)
        if m:
            index.setdefault(m["stem"], []).append((float(m["ra"]), float(m["dec"]), p))
    return index


def _size(paths):
    total = 0
    for p in paths:
        try:
            if p.is_dir():
                total += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            elif p.exists():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def target_files(text, target):
    """Files of target `text` (SkyCoord `target`) -> dict: name, images (cutout paths),
    frame_list (path or None), results (folder or None), cones (paths), n_images, size_bytes.
    Reads the frame list and lists the cache folders; no network."""
    name = target_name(text, target)
    frame_list = table_path(text, target)
    images, centre = [], at_time(target, Time.now())
    if frame_list.exists():
        frames = Table.read(frame_list)
        if len(frames):
            pos = at_time(target, Time(np.asarray(frames["mjd"], float), format="mjd"))
            n = len(frames)                    # no proper motion: one position for every frame
            ras = np.broadcast_to(pos.ra.deg, (n,))
            decs = np.broadcast_to(pos.dec.deg, (n,))
            centre = SkyCoord(ras[n // 2] * u.deg, decs[n // 2] * u.deg)
            index = _cutout_index()
            for url, ra, dec in zip(frames["access_url"], ras, decs):
                stem = str(url).rsplit("/", 1)[-1].removesuffix(".fits")
                for r, d, p in index.get(stem, ()):
                    if abs(r - ra) < CENTRE_TOL_DEG and abs(d - dec) < CENTRE_TOL_DEG:
                        images.append(p)
    else:
        frame_list = None
    cones = []
    for folder in (CACHE_ROOT / "gaia", CACHE_ROOT / "wise"):
        if folder.is_dir():
            for p in folder.iterdir():
                m = CONE_RE.match(p.name)
                if m and SkyCoord(float(m["ra"]) * u.deg, float(m["dec"]) * u.deg).separation(centre).deg < CONE_MATCH_DEG:
                    cones.append(p)
    res = results.target_dir(name)
    res = res if res.is_dir() else None
    images = sorted(set(images))
    size = _size(images) + _size(cones) + _size([p for p in (frame_list, res) if p is not None])
    return {"name": name, "images": images, "frame_list": frame_list, "results": res, "cones": cones,
            "n_images": len(images), "size_bytes": size}


def remove_target_files(text, target):
    """Delete every file of the target (see target_files) -> bytes freed. Missing files are fine."""
    files = target_files(text, target)
    for p in files["images"] + files["cones"] + ([files["frame_list"]] if files["frame_list"] else []):
        try:
            Path(p).unlink()
        except FileNotFoundError:
            pass
    if files["results"]:
        shutil.rmtree(files["results"], ignore_errors=True)
    results.forget(files["name"])
    return files["size_bytes"]
