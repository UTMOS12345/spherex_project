"""Lesson 3 - find every SPHEREx frame covering a target (IRSA SIA)."""
import re
from pathlib import Path

import numpy as np
import astropy.units as u
from astropy.table import Table, vstack
from astropy.time import Time
from astroquery.ipac.irsa import Irsa

from .net import with_retries
from .targets import at_time, target_name

KEEP = ["t_min", "t_max", "energy_bandpassname", "em_min", "em_max", "obs_id", "access_url"]
TABLE_DIR = Path("cache/frames")


def spherex_collections():
    """Wide-survey SPHEREx collections on IRSA, best first, e.g.
    ['spherex_dr2', 'spherex_dr1', 'spherex_qr3', 'spherex_qr2', 'spherex_qr'].
    Data Releases (dr) are the final reprocessing, so they rank above Quick Releases (qr);
    within each kind the higher number is newer. _deep and _cal collections are skipped.
    Any future release (qr4, dr2, ...) is picked up automatically."""
    tab = with_retries(Irsa.list_collections, servicetype="SIA", filter="spherex")
    found = []
    for n in (str(x) for x in tab["collection"]):
        m = re.fullmatch(r"spherex_(qr|dr)(\d*)", n)
        if m:
            kind, num = m.group(1), int(m.group(2) or 1)
            found.append((kind == "dr", num, n))          # dr before qr, then newest first
    return [n for *_, n in sorted(found, reverse=True)]


def find_frames(coord, collections=None, include_qr1=False):
    """Target SkyCoord -> Table of frames sorted by time, merged across all releases
    (DR and QR); when an exposure is in several releases, the best one wins.
    Columns: mjd, date, detector ('D1'..'D6'), band_um, obs_id, access_url, collection."""
    cols = collections or spherex_collections()
    if not include_qr1 and len(cols) > 1:
        cols = [c for c in cols if c != "spherex_qr"]
    now = at_time(coord, Time.now())                     # search where the star is now
    parts = []
    for rank, col in enumerate(cols):                    # rank 0 = newest release
        t = with_retries(Irsa.query_sia, pos=(now, 30 * u.arcsec), collection=col)
        print(f"  {col}: {len(t)} frames")
        if len(t):
            t = Table(t)[KEEP]
            t["collection"] = col
            t["rank"] = rank
            parts.append(t)
    if not parts:
        return Table(names=KEEP + ["collection", "mjd", "date", "detector", "band_um"])
    t = vstack(parts, metadata_conflicts="silent")

    # the same exposure in two releases has the same detector + start time: keep the newest
    t["key"] = [f"{b}_{round(float(m) * 86400)}" for b, m in zip(t["energy_bandpassname"], t["t_min"])]
    t.sort(["key", "rank"])
    _, first = np.unique(t["key"], return_index=True)
    t = t[np.sort(first)]

    t["mjd"] = (np.asarray(t["t_min"], float) + np.asarray(t["t_max"], float)) / 2
    t.sort("mjd")
    t["detector"] = [str(s).removeprefix("SPHEREx-") for s in t["energy_bandpassname"]]
    t["date"] = Time(t["mjd"], format="mjd").iso
    # centre of the DETECTOR's band, not the wavelength at the star (that is Lesson 10)
    t["band_um"] = np.round((np.asarray(t["em_min"], float) + np.asarray(t["em_max"], float)) / 2 * 1e6, 2)
    t.remove_columns(["key", "rank"])
    return t


def table_path(name, coord=None):
    """cache/frames/<safe target name>.ecsv - the one naming rule for frame lists."""
    safe = re.sub(r"[^A-Za-z0-9]+", "_", target_name(name, coord)).strip("_")
    return TABLE_DIR / f"{safe}.ecsv"


def load_or_find_frames(name, coord, refresh=False):
    """Like find_frames but saved to cache/frames/<name>.ecsv, so reruns work offline.
    refresh=True searches again (new SPHEREx data is released weekly).
    The file name comes from targets.target_name, so 'barnard', "Barnard's Star" and its
    coordinates all share cache/frames/Barnard_s_Star.ecsv."""
    path = table_path(name, coord)
    if path.exists() and not refresh:
        return Table.read(path)
    frames = find_frames(coord)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    frames.write(path, overwrite=True)
    return frames
