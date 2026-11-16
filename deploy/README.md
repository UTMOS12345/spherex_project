# Deploying the SPHEREx Flipbook

Target: a fresh DigitalOcean droplet, Ubuntu 24.04, 2 vCPU / 4 GB RAM / 50+ GB disk.
The app runs as the `spherex` system user behind nginx; a cron job follows the
`main` branch.

## 1. Bootstrap the server

```bash
ssh root@YOUR_DROPLET_IP
git clone --branch main https://github.com/UTMOS12345/spherex_project.git /srv/spherex
bash /srv/spherex/deploy/bootstrap.sh
```

This installs Python, nginx and certbot, creates the `spherex` user, builds
`/srv/spherex/.venv`, installs `/etc/systemd/system/spherex.service`, enables the
nginx site and adds `/etc/cron.d/spherex-deploy`. It does **not** download data.

Check it is up:

```bash
systemctl status spherex
curl -I http://127.0.0.1:8501
journalctl -u spherex -n 50 --no-pager
```

## 2. Fill the cache

The app runs with `SPHEREX_DEMO=1` (see `/etc/spherex.env`) and therefore never
downloads; it needs the frame lists and FITS cutouts in `/srv/spherex-cache`.

Fastest, from the machine that already has them:

```bash
rsync -av --info=progress2 cache/ root@YOUR_DROPLET_IP:/srv/spherex-cache/
ssh root@YOUR_DROPLET_IP 'chown -R spherex:spherex /srv/spherex-cache'
```

Or rebuild on the server (about 2 hours for the five demo targets):

```bash
sudo -u spherex bash -c 'set -a; . /etc/spherex.env; set +a; cd /srv/spherex && .venv/bin/python tools/prepare_demo.py --refresh --skip-explore'
```

Keep `SPHEREX_CACHE_MAX_GB` in `/etc/spherex.env` below the free disk space; the
LRU sweep only deletes `cache/cutouts/`, never `frames`, `gaia` or `wise`.

## 3. DNS and HTTPS

Point an `A` record (for example `flipbook.example.com`) at the droplet, then:

```bash
sed -i 's/server_name _;/server_name flipbook.example.com;/' /etc/nginx/sites-available/spherex
nginx -t && systemctl reload nginx
certbot --nginx -d flipbook.example.com
```

Open the firewall if it is enabled:

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

## 4. Updates

Merge to `main` and push; the cron job pulls and restarts within 5 minutes:

```bash
git push origin main
```

Apply immediately, or check what the cron job did:

```bash
sudo /usr/local/bin/spherex-deploy
tail -f /var/log/spherex-deploy.log
```

The deploy script restarts only when the branch head or `requirements.txt`
changes. To turn automatic deploys off:

```bash
rm /etc/cron.d/spherex-deploy
```

## Switching an existing server from `production` to `main`

Servers set up before 16 Nov 2026 follow `production`. The cron job runs the copy of
`deploy.sh` installed at `/usr/local/bin/spherex-deploy`, so updating the repo alone does
not move the server. As root:

```bash
cd /srv/spherex
sudo -H -u spherex git fetch origin
sudo -H -u spherex git switch main
install -m 0755 /srv/spherex/deploy/deploy.sh /usr/local/bin/spherex-deploy
/usr/local/bin/spherex-deploy
systemctl is-active spherex && curl -sI http://127.0.0.1:8501 | head -1
journalctl -u spherex -n 50 --no-pager | grep -i traceback || echo 'no tracebacks'
```

To go back: `BRANCH=production /usr/local/bin/spherex-deploy` after
`sudo -H -u spherex git switch production`.

## Integrating the teammate's frontend

```bash
git fetch origin frontend
git switch main
git merge --no-ff origin/frontend
git push origin main
```

## Troubleshooting

- **502 from nginx**: `systemctl status spherex`; usually the venv is missing or
  `pip install` failed. Re-run `deploy/bootstrap.sh`.
- **Blank page / disconnected**: the websocket upgrade headers are required; do
  not replace `nginx-spherex.conf` with a plain proxy block.
- **"not in cache/ (demo mode)"**: the cache is incomplete; rerun step 2.
- **Disk full**: lower `SPHEREX_CACHE_MAX_GB`, `systemctl restart spherex`, and
  run the deploy script (or restart) so the sweep runs.
- **Pinned wheels fail on Python 3.12**: the pins were validated on Python 3.14.
  Install 3.14 (`uv python install 3.14`) and rebuild the venv, or relax the pins
  in `requirements.txt` to the newest compatible versions.
