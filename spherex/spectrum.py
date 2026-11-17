"""Lesson 10 - spectrum: brightness of one target at every wavelength, during one visit."""
import numpy as np
from astropy.table import Table, vstack

from .download import get_cutouts
from .epochs import assign_epochs
from .photometry import measure_frame, release_name
from .progress import report, MEASURING
from .targets import at_times

# SPHEREx's six detectors; each is split into 17 channels -> 6 x 17 = 102 channels.
BANDS_UM = {1: (0.75, 1.09), 2: (1.10, 1.62), 3: (1.63, 2.41),
            4: (2.42, 3.82), 5: (3.83, 4.41), 6: (4.42, 5.00)}
CHANNELS_PER_BAND = 17


def channel_edges():
    """Approximate wavelength edges (micron) of the 102 channels: 17 per detector, spaced
    evenly in log(wavelength) (each SPHEREx channel has about the same resolving power)."""
    return {d: np.geomspace(lo, hi, CHANNELS_PER_BAND + 1) for d, (lo, hi) in BANDS_UM.items()}


MEASURE_DEG = 0.1         # cutout size the measurements ask for (served from any bigger cached file)


def spectrum_requests(frames, target, size_deg=MEASURE_DEG):
    """The get_cutouts requests spectrum() makes for these frames, in the same order."""
    return [(row["access_url"], pos, size_deg) for row, pos in zip(frames, at_times(target, frames["mjd"]))]


def spectrum(frames_of_epoch, target, r_px=2.0, size_deg=MEASURE_DEG, progress=None, paths=None):
    """Frames of ONE visit (all detectors) + target SkyCoord -> Table sorted by wavelength:
    wavelength_um, flux_mjy, err_mjy, flux_min_mjy (lower limit, saturated only), detector, mjd,
    n_bad, saturated, bad_flags, ok, release ('DR1', 'QR3', ...).
    Every frame sees the target at its own wavelength (the colour depends on where the
    star lands on the detector), so the frames of one visit together cover 0.75-5 micron.
    progress: optional callback (spherex.progress): "downloading images", then "measuring".
    paths: the get_cutouts result for spectrum_requests(frames_of_epoch, ...), when the caller
    has already fetched them (then nothing is downloaded and only "measuring" is reported)."""
    requests = spectrum_requests(frames_of_epoch, target, size_deg)
    positions = [pos for _, pos, _ in requests]
    if paths is None:
        paths = get_cutouts(requests, progress)
    n = len(frames_of_epoch)
    rows = []
    report(progress, MEASURING, 0, n)
    for i, (row, pos, path) in enumerate(zip(frames_of_epoch, positions, paths)):
        try:
            if isinstance(path, OSError):
                raise path
            m = measure_frame(path, pos, r_px)
        except OSError as e:
            print(f"  skipped {row['obs_id']} {row['detector']}: {e}")
            report(progress, MEASURING, i + 1, n)
            continue
        if np.isfinite(m["wavelength_um"]):
            m["release"] = release_name(row["collection"]) if "collection" in frames_of_epoch.colnames else ""
            rows.append(m)
        report(progress, MEASURING, i + 1, n)
    names = ["wavelength_um", "flux_mjy", "err_mjy", "flux_min_mjy", "detector", "mjd", "n_bad", "saturated",
             "bad_flags", "ok", "release"]
    if not rows:
        return Table(names=names)
    t = Table(rows)[names]
    t.sort("wavelength_um")
    for col, fmt in [("wavelength_um", ".3f"), ("flux_mjy", ".3f"), ("err_mjy", ".3f"), ("flux_min_mjy", ".1f"),
                     ("mjd", ".3f")]:
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
