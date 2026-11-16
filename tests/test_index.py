"""The targets index (paramost.index) and a target's files (spherex.cachefiles), no network."""
import json

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

import paramost.index as index
from spherex import cachefiles, download, frames, net, results


def test_record_and_newest_first(tmp_path):
    index.record(tmp_path, "A", name="A", text="a", n_images=3, size_bytes=10)
    index.record(tmp_path, "B", name="B", text="b", n_images=0, size_bytes=5)      # no images: hidden
    index.record(tmp_path, "C", name="C", text="c", n_images=1, size_bytes=1)
    assert [e["key"] for e in index.load_index(tmp_path)] == ["C", "A"]
    index.record(tmp_path, "A", settings={"view": "compare"})
    first = index.load_index(tmp_path)[0]
    assert first["key"] == "A" and first["settings"] == {"view": "compare"} and first["n_images"] == 3
    index.drop(tmp_path, "A")
    assert [e["key"] for e in index.load_index(tmp_path)] == ["C"]
    assert not list(tmp_path.glob(".*.part"))


def test_broken_index_is_rebuilt(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(index, "rebuild", lambda root: calls.append(root) or {"X": {"name": "X", "text": "x", "n_images": 1}})
    index.index_path(tmp_path).write_text("{not json")
    assert [e["key"] for e in index.load_index(tmp_path)] == ["X"] and calls
    assert json.loads(index.index_path(tmp_path).read_text())["targets"]["X"]["text"] == "x"


def test_names_from_typed_coordinates():
    (ra, dec), (_, dec2) = index._key_positions("17h57m49_5s_04d41m36_2s")
    assert abs(ra - 269.45625) < 1e-9 and abs(dec - 4.6933889) < 1e-6 and dec2 == -dec
    assert index._key_positions("133_795_7_245") == [(133.795, 7.245), (133.795, -7.245)]
    assert index._key_positions("Barnard_s_Star") == []


def test_target_files_takes_only_its_own_images(tmp_path, monkeypatch):
    for mod in (net, cachefiles):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(cachefiles, "CACHE_DIR", tmp_path / "cutouts")
    monkeypatch.setattr(download, "CACHE_DIR", tmp_path / "cutouts")
    monkeypatch.setattr(frames, "TABLE_DIR", tmp_path / "frames")
    monkeypatch.setattr(results, "RESULTS_DIR", tmp_path / "results")
    star = SkyCoord(150.0 * u.deg, 2.0 * u.deg)
    url = "https://irsa.example/level2_X_1D2_spx_l2b.fits"
    (tmp_path / "frames").mkdir()
    Table({"mjd": [60000.0], "access_url": [url]}).write(tmp_path / "frames" / "150_2.ecsv")
    (tmp_path / "cutouts").mkdir()
    mine = download.cache_path(url, star, 0.25)
    other = download.cache_path(url, SkyCoord(150.03 * u.deg, 2.0 * u.deg), 0.25)   # a neighbour, same frame
    mine.write_bytes(b"1" * 100)
    other.write_bytes(b"2" * 100)
    files = cachefiles.target_files("150 2", star)
    assert files["images"] == [mine] and files["n_images"] == 1
    cachefiles.remove_target_files("150 2", star)
    assert not mine.exists() and other.exists() and not (tmp_path / "frames" / "150_2.ecsv").exists()
