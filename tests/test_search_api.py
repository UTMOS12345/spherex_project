"""api.find_movers and `paramost search` on synthetic visits (no cache, no network)."""
import numpy as np
import pytest

from spherex import api, search
from paramost import cli
from test_search import gauss, visits


@pytest.fixture
def field(monkeypatch):
    eps = visits([lambda i: gauss(60 - 1.5 * i, 60, 4.0),          # a mover
                  lambda i: gauss(30, 90, 2.0 if i == 2 else 0.0)],  # appears in the last visit
                 n_visits=3)
    for e in eps:
        e["detectors_used"] = "D2"
    monkeypatch.setattr(api, "_epochs", lambda *a, **k: (None, None, eps))
    monkeypatch.setattr(search, "visit_paths", lambda *a, **k: [[] for _ in eps])   # no images: no saturation cut
    return eps


def test_find_movers_table(field):
    stages = []
    t = api.find_movers("somewhere", catalogues=False, asteroids=False, progress=lambda s, d, n: stages.append(s))
    assert list(t.colnames[:len(api.SEARCH_COLUMNS)]) == api.SEARCH_COLUMNS
    assert list(t["rank"]) == list(range(1, len(t) + 1))
    assert list(t["peak_to_noise"]) == sorted(t["peak_to_noise"], reverse=True)
    assert "mover" in set(t["type"]) and set(t["label"]) == {"unexplained"}
    assert "not a detection" in t.meta["note"] and t.meta["cuts"]["saturation_cut"] is False
    assert t.meta["settings"]["visits"] == 3 and "measuring" in stages
    again = api.find_movers("somewhere", catalogues=False, asteroids=False)
    assert all((np.asarray(t[c]) == np.asarray(again[c])).all() for c in t.colnames
               if t[c].dtype.kind != "f") and np.allclose(t["peak_to_noise"], again["peak_to_noise"])


def test_find_movers_bad_settings(field):
    with pytest.raises(ValueError):
        api.find_movers("somewhere", method="median")
    with pytest.raises(ValueError):
        api.find_movers("somewhere", pairs="nearest")


def test_cli_search_prints_and_writes(field, tmp_path, capsys):
    csv, thumbs = tmp_path / "c.csv", tmp_path / "th"
    code = cli.main(["search", "somewhere", "--no-catalogues", "--no-asteroids", "--csv", str(csv),
                     "--thumbnails", str(thumbs)])
    out = capsys.readouterr().out
    assert code == 0 and "rank" in out and "not a detection" in out and "removed:" in out
    assert csv.read_text().startswith("rank,pair")
    n = int(out.split(" candidates (")[0].rsplit("\n", 1)[-1])
    assert n > 0 and len(list(thumbs.glob("*.png"))) == n and f"{n} thumbnails" in out
