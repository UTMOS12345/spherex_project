"""paramost render: options, targets file, offline checks, warnings in summary.json, exit codes.
The api is replaced by small fakes, so these tests need no cache and no network."""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest
from astropy.table import Table

from paramost import render
from paramost.cli import main
from spherex import api, net


def _fig(value):
    fig, ax = plt.subplots(figsize=(2, 2))
    ax.imshow(np.full((4, 4), value), vmin=0, vmax=1)
    return fig


def _table(warning=None):
    t = Table({"mjd": [60000.0, 60001.5], "flux_mjy": [1.0, np.nan], "state": ["ok", "masked"]})
    if warning:
        t.meta["warning"] = warning
    return t


@pytest.fixture
def fake_api(monkeypatch):
    """The api functions render calls, faked. missing: call name -> (missing, total) images."""
    monkeypatch.setenv("SPHEREX_DEMO", "0")
    was = net.DEMO_MODE
    state = {"missing": {}, "calls": []}

    def count_downloads(fn, *args, **kwargs):
        return dict(zip(("missing", "total"), state["missing"].get(fn.__name__, (0, 10))))

    def epochs(text, **kw):
        state["calls"].append("epochs")
        return Table({"index": [0, 1], "date": ["2025-05-05", "2026-04-27"], "few_frames": [True, False],
                      "n_min": [3, 21], "releases": ["DR1", "DR1, QR3"]})

    def record(name, result):
        def fn(*args, **kwargs):
            state["calls"].append(name)
            return result() if callable(result) else result
        fn.__name__ = name
        return fn

    monkeypatch.setattr(api, "resolve", lambda text: {"name": text, "ra": 1.0, "dec": 2.0})
    monkeypatch.setattr(api, "defaults", lambda text: {"detector": "D6", "band": 4.5, "tol": 0.02})
    monkeypatch.setattr(api, "target_files", lambda text: {"frame_list": "cached.ecsv"})
    monkeypatch.setattr(api, "count_downloads", count_downloads)
    epochs.__name__ = "epochs"
    monkeypatch.setattr(api, "epochs", epochs)
    monkeypatch.setattr(api, "flipbook", record("flipbook", b"GIF89a fake"))
    monkeypatch.setattr(api, "picture", record("picture", lambda: _fig(0.5)))
    monkeypatch.setattr(api, "overlay_figure", record("overlay_figure", lambda: (_fig(0.2), {"drawn": ["gaia"], "failed": []})))
    monkeypatch.setattr(api, "light_curve_figure", record("light_curve_figure",
                                                          lambda: (_fig(0.3), _table("The target is saturated."))))
    monkeypatch.setattr(api, "spectrum_figure", record("spectrum_figure", lambda: (_fig(0.4), _table())))
    monkeypatch.setattr(api, "flags_figure", record("flags_figure", lambda: (_fig(0.6), _table())))
    yield state
    net.set_demo_mode(was)


def _summary(folder):
    return json.loads((folder / "summary.json").read_text())


# ------------------------------------------------------------------ options and targets file
def test_products():
    assert render.parse_products(None) == render.DEFAULT_PRODUCTS
    assert render.parse_products("spectrum, video") == ("video", "spectrum")       # in the fixed order
    assert render.parse_products("light_curve") == ("light-curve",)
    every = render.parse_products("all")
    assert set(every) == set(render.PRODUCTS) - (set() if hasattr(api, "find_movers") else {"search"})
    with pytest.raises(render.UsageError, match="unknown product colour"):
        render.parse_products("video,colour")


def test_slug():
    assert render.slug("Barnard's Star") == "barnard_s_star"
    assert render.slug("WISE 0855") == "wise_0855"
    assert render.slug("133.795 -7.245") == "133_795_7_245"


def test_targets_file(tmp_path):
    f = tmp_path / "targets.txt"
    f.write_text("# the gallery\n\nWISE 0855 | --detector D5 --fov 6   # comment\nBarnard's Star\n"
                 "133.795 -7.245 | --products video --name coords\n", encoding="utf-8")
    import argparse
    p = argparse.ArgumentParser()
    render.add_arguments(p)
    base = p.parse_args(["--targets", str(f), "--out", str(tmp_path / "out"), "--fov", "4"])
    jobs = render.jobs_from_args(base)
    assert [(t, str(folder.name)) for t, _, folder in jobs] == [
        ("WISE 0855", "wise_0855"), ("Barnard's Star", "barnard_s_star"), ("133.795 -7.245", "coords")]
    (_, w, _), (_, b, _), (_, c, _) = jobs
    assert (w.detector, w.fov) == ("D5", 6.0)
    assert (b.detector, b.fov) == (None, 4.0)                    # the command line's settings
    assert c.products == "video"
    f.write_text("WISE 0855 | --colour red\n")
    with pytest.raises(render.UsageError, match="line 1"):
        render.read_targets(f, base)


def test_usage_errors(tmp_path, capsys):
    assert main(["render", "--out", str(tmp_path)]) == render.EXIT_USAGE
    assert main(["render", "X", "--targets", "t.txt", "--out", str(tmp_path)]) == render.EXIT_USAGE
    assert main(["render", "X", "--out", str(tmp_path), "--partial"]) == render.EXIT_USAGE
    assert main(["render", "X", "--out", str(tmp_path), "--products", "nope"]) == render.EXIT_USAGE
    assert "unknown product nope" in capsys.readouterr().err


# ------------------------------------------------------------------ running
def test_every_product_made(fake_api, tmp_path):
    out = tmp_path / "w"
    code = main(["render", "WISE 0855", "--out", str(out), "--offline",
                 "--products", "video,difference,overlay,light-curve,spectrum,deep,flags"])
    assert code == render.EXIT_OK
    for name in ["video.gif", "difference.png", "overlay.png", "light_curve.png", "light_curve.csv",
                 "spectrum.png", "spectrum.csv", "deep.png", "flags.png", "flags.csv"]:
        assert (out / name).stat().st_size > 0, name
    assert (out / "video.gif").read_bytes() == b"GIF89a fake"
    s = _summary(out)
    assert s["products_failed"] == {} and len(s["products_made"]) == 7
    assert s["settings"]["detector"] == "D6" and s["settings"]["band"] == 4.5    # from api.defaults
    assert s["offline"] is True and "timings_seconds" in s
    warnings = {(w["product"], w["warning"]) for w in s["warnings"]}
    # the api's own warning survives, and the few-frames / mixed-release notes of the pictures
    assert ("light-curve", "The target is saturated.") in warnings
    assert any(p == "video" and w.startswith("few frames: unreliable: picture 0 (2025-05-05)") for p, w in warnings)
    assert any(p == "video" and "more than one data release (DR1, QR3)" in w for p, w in warnings)
    assert s["products"]["overlay"]["notes"]["drawn"] == ["gaia"]
    csv = (out / "light_curve.csv").read_text()
    assert csv.splitlines()[0] == "mjd,flux_mjy,state" and "saturated" not in csv       # no meta in the CSV


def test_offline_missing_images_fail_clearly(fake_api, tmp_path):
    out = tmp_path / "w"
    out.mkdir()
    (out / "spectrum.png").write_bytes(b"old")                       # from an earlier run
    fake_api["missing"]["spectrum_figure"] = (79, 100)
    code = main(["render", "WISE 0855", "--out", str(out), "--offline", "--products", "light-curve,spectrum"])
    assert code == render.EXIT_FAILED
    assert "spectrum_figure" not in fake_api["calls"]               # not made from the 21 cached images
    assert not (out / "spectrum.png").exists()                       # no stale file that looks current
    s = _summary(out)
    assert s["products_made"] == ["light-curve"]
    assert "79 of the 100 images" in s["products_failed"]["spectrum"]


def test_offline_partial(fake_api, tmp_path):
    fake_api["missing"]["spectrum_figure"] = (79, 100)
    out = tmp_path / "w"
    code = main(["render", "WISE 0855", "--out", str(out), "--offline", "--partial", "--products", "spectrum"])
    assert code == render.EXIT_OK
    s = _summary(out)
    assert s["products_partial"] == ["spectrum"]
    assert s["warnings"][0]["warning"].startswith("partial: made from the 21 of 100 images in the cache")


def test_offline_needs_the_frame_list(fake_api, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "target_files", lambda text: {"frame_list": None})
    out = tmp_path / "w"
    assert main(["render", "New Star", "--out", str(out), "--offline"]) == render.EXIT_FAILED
    assert "no frame list in the cache" in _summary(out)["error"]
    assert fake_api["calls"] == []


def test_a_failing_product_does_not_stop_the_rest(fake_api, tmp_path, monkeypatch):
    def broken(*a, **k):
        raise ValueError("There are only 2 visits.")
    monkeypatch.setattr(api, "spectrum_figure", broken)
    out = tmp_path / "w"
    code = main(["render", "WISE 0855", "--out", str(out), "--offline", "--products", "video,spectrum,deep"])
    assert code == render.EXIT_FAILED
    s = _summary(out)
    assert s["products_made"] == ["video", "deep"]
    assert s["products_failed"] == {"spectrum": "There are only 2 visits."}


def test_downloads_need_yes_unattended(fake_api, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", open(__file__))                # not a terminal
    fake_api["missing"]["epochs"] = (12, 40)
    out = tmp_path / "w"
    assert main(["render", "WISE 0855", "--out", str(out), "--products", "video"]) == render.EXIT_NOT_CONFIRMED
    assert "12 images to download" in capsys.readouterr().out
    assert "flipbook" not in fake_api["calls"] and not out.exists()
    assert main(["render", "WISE 0855", "--out", str(out), "--products", "video", "--yes"]) == render.EXIT_OK
    assert (out / "video.gif").exists()


def test_targets_run_one_after_another(fake_api, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("WISE 0855\nRW Aur | --products video\n")
    out = tmp_path / "gallery"
    assert main(["render", "--targets", str(f), "--out", str(out), "--offline", "--products", "video,deep"]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["rw_aur", "wise_0855"]
    assert _summary(out / "rw_aur")["products_made"] == ["video"]
    assert _summary(out / "wise_0855")["products_made"] == ["video", "deep"]


# ------------------------------------------------------------------ byte-identical output
def _png_chunks(data):
    import struct
    i, out = 8, []
    while i < len(data):
        n, = struct.unpack(">I", data[i:i + 4])
        out.append(data[i + 4:i + 8].decode())
        i += 12 + n
    return out


def test_png_has_no_text_metadata(tmp_path):
    render.write_file(tmp_path / "a.png", _fig(0.5))
    chunks = _png_chunks((tmp_path / "a.png").read_bytes())
    assert "tEXt" not in chunks and "iTXt" not in chunks and "tIME" not in chunks, chunks


def test_same_inputs_same_bytes(fake_api, tmp_path, monkeypatch):
    """Two runs with unchanged inputs (and --no-timings) write byte-identical files, even
    when the clock and the matplotlib version string differ between them."""
    import time as _time
    args = ["--offline", "--no-timings", "--products", "video,difference,overlay,light-curve,spectrum,deep,flags"]
    assert main(["render", "WISE 0855", "--out", str(tmp_path / "a"), *args]) == 0
    real = _time.time
    monkeypatch.setattr(_time, "time", lambda: real() + 86400 * 400)          # a year later
    monkeypatch.setattr(matplotlib, "__version__", "9.9.9")
    assert main(["render", "WISE 0855", "--out", str(tmp_path / "b"), *args]) == 0
    a = {p.name: p.read_bytes() for p in (tmp_path / "a").iterdir()}
    b = {p.name: p.read_bytes() for p in (tmp_path / "b").iterdir()}
    assert a.keys() == b.keys() and len(a) == 11
    assert [k for k in a if a[k] != b[k]] == []
