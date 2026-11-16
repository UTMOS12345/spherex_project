# Self-hosting the app (optional)

> **There is no public instance.** The demo server that ran during the NASA Space Apps Challenge
> has been shut down. This page is for anyone who wants to host their own copy; to just use the
> app, install it on your computer (see the README).

The app is meant to run on your own computer (`pipx install`, see the README). Hosting it is
optional: one Ubuntu server that serves the app read-only to visitors. The step-by-step server
guide is [deploy/README.md](../deploy/README.md); this page is the overview.

## What the server runs

- `deploy/spherex.service` (systemd) runs `python -m paramost --no-browser --address 127.0.0.1
  --port 8501` in `/srv/spherex`, a git checkout, as the `spherex` user, behind nginx
  (`deploy/nginx-spherex.conf`).
- `/etc/spherex.env` (from `deploy/spherex.env.example`) sets the server's environment:
  - `SPHEREX_DEMO=1`: the app starts with Offline on, nothing is downloaded, every server call
    gets one short try, and visitors see no remove buttons under "your targets".
  - `SPHEREX_CACHE=/srv/spherex-cache`: the server's own cache, outside the checkout.
  - `SPHEREX_CACHE_MAX_GB`, `SPHEREX_CACHE_POLICY`, `SPHEREX_CACHE_TTL_DAYS`: a bounded image
    cache (recommended: 25, `evict`, 0).
  - `SPHEREX_DEMO_DIR`, `SPHEREX_OUT_DIR`: where the tools below write.
- `deploy/deploy.sh`, installed as `/usr/local/bin/spherex-deploy`, is run by cron every 5
  minutes: it pulls the branch and restarts the service when the code or `requirements.txt`
  changed (installing the exact versions from `requirements.txt`).

Short version (details in deploy/README.md):

```
bash deploy/bootstrap.sh                          # as root on a fresh server
rsync -av cache/ root@SERVER:/srv/spherex-cache/  # or fill it there with tools/prepare_demo.py
```

## Servers set up before version 1.0

The systemd unit and the deploy script on a server are copies made at setup, which `git pull`
does not update. A server set up before 1.0 (when the app was `app.py` at the root) re-installs
them once:

```
install -m 0644 /srv/spherex/deploy/spherex.service /etc/systemd/system/spherex.service
install -m 0755 /srv/spherex/deploy/deploy.sh /usr/local/bin/spherex-deploy
systemctl daemon-reload && systemctl restart spherex
```

Until then, `app.py` at the root of the checkout forwards to `paramost/app.py`.

## Demo backups and extra products (tools/)

Run from the checkout, with the server's environment:

```
SPHEREX_DEMO=1 .venv/bin/python tools/prepare_demo.py --skip-explore    # video, difference, overlay, light curve, spectrum
.venv/bin/python tools/make_gallery.py                                  # every other product, demo/STATUS.md, demo/index.html
```

`tools/prepare_demo.py` downloads what the five test targets need (`--refresh` searches IRSA
for new data, `--all-frames` downloads every frame) and writes backup results to
`SPHEREX_DEMO_DIR` (default `demo/`); `tools/make_gallery.py` writes every other product and
`demo/index.html`, downloading what a product cannot do without; `tools/explore.py` writes
extra products to `SPHEREX_OUT_DIR` (default `out/`). `tools/strip_psf.py IN OUT` makes slim
copies of old cutouts that still hold the PSF layer.

## Docker instead of systemd

The image runs the same app: `docker run -p 8501:8501 -v cache:/data/cache
-e SPHEREX_DEMO=1 ghcr.io/utmos12345/paramost:1.0.0` behind any reverse proxy.
