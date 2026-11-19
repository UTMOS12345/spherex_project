"""False-positive control for the blind search: every candidate it reports is a false positive.

    python tools/search_null_control.py out/null                    # the five challenge fields
    python tools/search_null_control.py out/null "WISE 0855:D6"     # one field (target:detector)

Each visit's frames are split into two interleaved halves (alternate frames, in time order), each
half is stacked on its own, and the two halves of the same visit are differenced and searched
exactly like a visit pair: same detection, cuts, classification and catalogues as api.find_movers.
The halves cover the same days, so nothing in the field moved or changed measurably between them
(Barnard's Star, the fastest-moving star known, moves 0.07 px in a week): whatever survives the cuts
is a false positive, apart from asteroids, which SkyBoT labels.

The halves have half the frames of a visit, so their stacks are noisier than real visit stacks:
this is a pessimistic estimate of the false positives per visit pair.

Both halves must be on one sky grid. make_epochs centres its grid on the target at the mid-time of
the frames it is given, which differs between the halves (by 0.11 px for Barnard's Star, enough to
make every star leave a residual), so this script makes make_epochs use the grid of the whole
frame list for both halves. That replacement is local to this script; the library is unchanged.
Demo mode: it never downloads.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))   # repo root, so tools/ can import spherex
import json
import os
import time

import numpy as np

from spherex import api, net, search
from spherex import epochs as E
from spherex.epochs import assign_epochs, make_epochs, parse_detectors

FIELDS = ["Barnard's Star:D2", "Epsilon Indi B:D5", "WISE 0855:D6", "RW Aur:D1", "R Draconis:D3"]


def halves(name, det, clip):
    """Two lists of stacks, one per half, on one grid -> (frames, target, eps_even, eps_odd)."""
    target, frames = api._load(name)
    dets = parse_detectors(det)
    f = assign_epochs(frames[np.isin(frames["detector"], dets)].copy(), 30, 60)
    f.sort("mjd")
    half = {0: [], 1: []}
    for e in sorted(set(f["epoch"])):
        for k, r in enumerate(np.where(f["epoch"] == e)[0]):
            half[k % 2].append(r)
    real_grid = E.epoch_grid
    E.epoch_grid = lambda frames_, target_, a, p: real_grid(f, target_, a, p)   # one grid for both halves
    try:
        out = [make_epochs(f[sorted(half[h])], target, det, grid_arcmin=10.0, clip=clip) for h in (0, 1)]
    finally:
        E.epoch_grid = real_grid
    return f, target, out[0], out[1]


def run_field(name, det, clip):
    t0 = time.time()
    f, target, even, odd = halves(name, det, clip)
    dets = parse_detectors(det)
    totals = {c: 0 for c in ("residuals", *search.CUTS, "kept", "rescued_lobes")}
    rows, pairs = [], 0
    for ea in even:
        match = [e for e in odd if e["visit"] == ea["visit"]]
        if not match:
            continue
        eb = dict(match[0], wcs=ea["wcs"])               # the same grid (built from the same frames)
        pair = [ea, eb]
        pairs += 1
        paths = search.visit_paths(f, target, pair, dets, 0.25)
        sat = [search.saturation_map(p, ea["wcs"], ea["image"].shape) for p in paths] if all(paths) else None
        cut, summary = search.apply_cuts(search.find_residuals(pair), pair, sat)
        for c in totals:
            totals[c] += summary[c]
        cands, _ = search.crossmatch(search.classify(cut, pair), pair, asteroids=True)
        for r in cands:
            rows.append(dict(visit=int(ea["visit"]), date=ea["date"], frames=[int(ea["n_frames"]), int(eb["n_frames"])],
                             type=str(r["type"]), peak_to_noise=round(float(r["peak_to_noise"]), 1),
                             sign=int(r["sign"]), change=round(float(r["change"]), 2), label=str(r["label"]),
                             gaia_sep=round(float(r["gaia_sep_arcsec"]), 1), gaia_g=float(r["gaia_g"]),
                             saturated=bool(r["saturated"]), ra=float(r["ra"]), dec=float(r["dec"])))
    return dict(field=f"{name} {det}", clip=clip, null_pairs=pairs, cuts=totals, candidates=len(rows),
                unexplained=sum(r["label"] == "unexplained" for r in rows),
                types={k: sum(r["type"] == k for r in rows) for k in ("mover", "variable", "single")},
                seconds=round(time.time() - t0, 1), rows=rows)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    out_dir, fields = argv[0], argv[1:] or FIELDS
    os.makedirs(out_dir, exist_ok=True)
    net.set_demo_mode(True)
    runs = []
    for spec in fields:
        name, det = spec.rsplit(":", 1)
        for clip in (True, False):
            r = run_field(name, det, clip)
            runs.append(r)
            print(f"{r['field']} clip={clip}: {r['null_pairs']} null pairs, {r['candidates']} false candidates "
                  f"({r['unexplained']} unexplained; {r['types']}); {r['seconds']} s", flush=True)
            json.dump(runs, open(os.path.join(out_dir, "search_null_control.json"), "w"), indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
