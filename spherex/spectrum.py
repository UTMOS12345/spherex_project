"""Lesson 10 - spectrum: brightness of one target at every wavelength, during one visit."""
import numpy as np
from astropy.table import Table, vstack
from astropy.time import Time

from .download import get_cutout
from .epochs import assign_epochs
from .photometry import measure_frame
from .targets import at_time

# SPHEREx's six detectors; each is split into 17 channels -> 6 x 17 = 102 channels.
BANDS_UM = {1: (0.75, 1.09), 2: (1.10, 1.62), 3: (1.63, 2.41),
            4: (2.42, 3.82), 5: (3.83, 4.41), 6: (4.42, 5.00)}
CHANNELS_PER_BAND = 17


def channel_edges():
    """Approximate wavelength edges (micron) of the 102 channels: 17 per detector, spaced
    evenly in log(wavelength) (each SPHEREx channel has about the same resolving power)."""
    return {d: np.geomspace(lo, hi, CHANNELS_PER_BAND + 1) for d, (lo, hi) in BANDS_UM.items()}


def spectrum(frames_of_epoch, target, r_px=2.0, size_deg=0.1):
    """Frames of ONE visit (all detectors) + target SkyCoord -> Table sorted by wavelength:
    wavelength_um, flux_mjy, err_mjy, detector, mjd, n_bad, saturated, bad_flags, ok.
    Every frame sees the target at its own wavelength (the colour depends on where the
    star lands on the detector), so the frames of one visit together cover 0.75-5 micron."""
    rows = []
    for row in frames_of_epoch:
        pos = at_time(target, Time(row["mjd"], format="mjd"))
        try:
            m = measure_frame(get_cutout(row["access_url"], pos, size_deg), pos, r_px)
        except OSError as e:
            print(f"  skipped {row['obs_id']} {row['detector']}: {e}")
            continue
        if np.isfinite(m["wavelength_um"]):
            rows.append(m)
    names = ["wavelength_um", "flux_mjy", "err_mjy", "detector", "mjd", "n_bad", "saturated", "bad_flags", "ok"]
    if not rows:
        return Table(names=names)
    t = Table(rows)[names]
    t.sort("wavelength_um")
    for col, fmt in [("wavelength_um", ".3f"), ("flux_mjy", ".3f"), ("err_mjy", ".3f"), ("mjd", ".3f")]:
        t[col].info.format = fmt
    return t


def bin_to_channels(spec):
    """Usable points of a spectrum -> one row per channel that has data:
    detector, channel (1-17), wavelength_um (channel centre), flux_mjy (mean), err_mjy, n."""
    good = spec[spec["ok"]]
    out = []
    for d, edges in channel_edges().items():
        for c in range(CHANNELS_PER_BAND):
            sel = good[(good["detector"] == d) & (good["wavelength_um"] >= edges[c]) &
                       (good["wavelength_um"] < edges[c + 1])]
            if len(sel) == 0:
                continue
            f = np.asarray(sel["flux_mjy"], float)
            e = np.asarray(sel["err_mjy"], float)
            err = np.std(f) / np.sqrt(len(f)) if len(f) > 1 else e[0]
            out.append((d, c + 1, float(np.sqrt(edges[c] * edges[c + 1])), float(f.mean()),
                        float(max(err, np.sqrt(np.sum(e ** 2)) / len(f))), len(f)))
    return Table(rows=out, names=["detector", "channel", "wavelength_um", "flux_mjy", "err_mjy", "n"]) \
        if out else Table(names=["detector", "channel", "wavelength_um", "flux_mjy", "err_mjy", "n"])


def epoch_frames(frames, epoch=0, gap_days=30, max_len_days=60):
    """All frames (every detector) of visit number `epoch` -> table. epoch=-1 = latest visit."""
    frames = assign_epochs(frames, gap_days, max_len_days)
    ids = sorted(set(frames["epoch"]))
    return frames[frames["epoch"] == ids[epoch]]
