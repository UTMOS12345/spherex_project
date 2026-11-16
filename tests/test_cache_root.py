"""Where the cache lives: SPHEREX_CACHE, else an existing checkout cache/, else the user cache."""
from pathlib import Path

from spherex import net


def test_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("SPHEREX_CACHE", str(tmp_path / "c"))
    assert net.default_cache_root() == tmp_path / "c"


def test_checkout_cache_is_kept(monkeypatch, tmp_path):
    monkeypatch.delenv("SPHEREX_CACHE", raising=False)
    repo = tmp_path / "repo"
    (repo / "spherex").mkdir(parents=True)
    (repo / "cache").mkdir()
    (repo / "pyproject.toml").write_text("")
    monkeypatch.setattr(net, "__file__", str(repo / "spherex" / "net.py"))
    assert net.default_cache_root() == repo / "cache"


def test_installed_copy_uses_the_user_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("SPHEREX_CACHE", raising=False)
    site = tmp_path / "site-packages"
    (site / "spherex").mkdir(parents=True)           # no cache/, no .git, no pyproject.toml
    monkeypatch.setattr(net, "__file__", str(site / "spherex" / "net.py"))
    import platformdirs
    monkeypatch.setattr(platformdirs, "user_cache_dir", lambda name, appauthor=None: str(tmp_path / "user" / name))
    assert net.default_cache_root() == tmp_path / "user" / "paramost"
