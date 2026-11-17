"""Player drawing (api._player_pngs): the same pixels as drawing every picture from scratch."""
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import Normalize
from PIL import Image

from spherex import api
from spherex.diff import shared_norm


def _scratch_pngs(images, markers, titles, norm, cmap):
    """What player_html did before: clear the axes and build every artist for every picture."""
    out = []
    fig, ax = plt.subplots(figsize=(6, 6))
    for img, (x, y), title in zip(images, markers, titles):
        ax.clear()
        ax.imshow(img, origin="lower", cmap=cmap, norm=norm)
        ax.scatter([x], [y], s=400, facecolors="none", edgecolors="lime", lw=1.2)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(title, fontsize=10)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
        out.append(buf.getvalue())
    plt.close(fig)
    return out


def _pixels(png):
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


def _pictures(n=5, shape=(80, 80)):
    rng = np.random.default_rng(4)
    images = [rng.normal(size=shape) for _ in range(n)]
    images[-1][10:20, 30:33] = np.nan                      # a hole
    images[0] += 40 * np.exp(-((np.arange(80) - 40) ** 2)[None, :] / 8)   # a bright stripe
    markers = [(40.0 + i * 0.37, 39.5 - i * 0.21) for i in range(n)]
    titles = [f"Target  D2  2025-0{i + 1}-01  ({10 + i} frames)" for i in range(n)]
    titles[1] += "\nfew frames: unreliable"                # a two-line title changes the crop
    titles[-1] = "A much longer title than the others, which widens the picture's crop"
    return images, markers, titles


@pytest.mark.parametrize("kind", ["normal", "difference"])
def test_player_pixels_match_drawing_from_scratch(kind):
    images, markers, titles = _pictures()
    if kind == "normal":
        norm, cmap = shared_norm(images), "gray"
    else:
        norm, cmap = Normalize(-3, 3), "RdBu_r"
    new = api._draw_pictures(images, markers, titles, norm, cmap)
    old = _scratch_pngs(images, markers, titles, norm, cmap)
    assert len(new) == len(old) == len(images)
    for a, b in zip(new, old):
        pa, pb = _pixels(a), _pixels(b)
        assert pa.shape == pb.shape and np.array_equal(pa, pb)


def test_player_reports_progress_and_closes_its_figure():
    images, markers, titles = _pictures(3)
    seen = []
    n_before = len(plt.get_fignums())
    api._player_pngs(images, markers, titles, shared_norm(images), "gray", lambda *a: seen.append(a))
    assert [a[1:] for a in seen] == [(0, 3), (1, 3), (2, 3), (3, 3)]
    assert len(plt.get_fignums()) == n_before


def test_parallel_drawing_same_pixels(monkeypatch):
    """Many pictures with the workers running: drawn in chunks by other processes, the same
    pixels and order as one process; never starts workers by itself."""
    from spherex import workers
    monkeypatch.setenv("SPHEREX_WORKERS", "3")
    workers._shutdown()
    monkeypatch.setattr(workers, "_failed", False)
    images, markers, titles = _pictures(5)
    images, markers, titles = images * 4, markers * 4, [f"{t} #{i}" for i, t in enumerate(titles * 4)]
    norm = shared_norm(images)
    one = api._draw_pictures(images, markers, titles, norm, "gray")
    assert api._player_pngs(images, markers, titles, norm, "gray") and workers._pool is None   # not started
    workers.prestart()
    seen = []
    many = api._player_pngs(images, markers, titles, norm, "gray", lambda *a: seen.append(a[1]))
    try:
        assert len(many) == len(one) == 20
        for a, b in zip(many, one):
            assert np.array_equal(_pixels(a), _pixels(b))
        assert seen[0] == 0 and seen[-1] == 20 and seen == sorted(seen)
    finally:
        workers._shutdown()
