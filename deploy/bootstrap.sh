#!/usr/bin/env bash
# One-shot setup on a fresh Ubuntu 22.04/24.04 droplet. Run as root.
#
#   git clone --branch main https://github.com/UTMOS12345/spherex_project.git /srv/spherex
#   bash /srv/spherex/deploy/bootstrap.sh
#
# Or copy this directory to the server and run it; it clones the repo itself.
set -euo pipefail

REPO="${REPO:-https://github.com/UTMOS12345/spherex_project.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/srv/spherex}"
CACHE_DIR="${CACHE_DIR:-/srv/spherex-cache}"

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root: sudo bash deploy/bootstrap.sh" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx

if ! id spherex >/dev/null 2>&1; then
    getent group spherex >/dev/null || groupadd --system spherex
    useradd --system --gid spherex --no-create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin spherex
fi

if [ ! -d "$APP_DIR/.git" ]; then
    mkdir -p "$(dirname "$APP_DIR")"
    if [ -d "$APP_DIR" ] && [ -n "$(ls -A "$APP_DIR" 2>/dev/null)" ]; then
        echo "error: $APP_DIR exists and is not a git checkout; move it away first" >&2
        exit 1
    fi
    git clone --branch "$BRANCH" "$REPO" "$APP_DIR"
fi

mkdir -p "$CACHE_DIR" "$APP_DIR/demo" "$APP_DIR/out"
chown -R spherex:spherex "$APP_DIR" "$CACHE_DIR"

if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    sudo -H -u spherex python3 -m venv "$APP_DIR/.venv"
fi
sudo -H -u spherex "$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
sudo -H -u spherex "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f /etc/spherex.env ]; then
    install -m 0640 -o root -g spherex "$APP_DIR/deploy/spherex.env.example" /etc/spherex.env
fi

install -m 0644 "$APP_DIR/deploy/spherex.service" /etc/systemd/system/spherex.service
systemctl daemon-reload
systemctl enable --now spherex

install -m 0644 "$APP_DIR/deploy/nginx-spherex.conf" /etc/nginx/sites-available/spherex
ln -sf /etc/nginx/sites-available/spherex /etc/nginx/sites-enabled/spherex
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

install -m 0755 "$APP_DIR/deploy/deploy.sh" /usr/local/bin/spherex-deploy
cat > /etc/cron.d/spherex-deploy <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
*/5 * * * * root /usr/local/bin/spherex-deploy >> /var/log/spherex-deploy.log 2>&1
CRON
chmod 0644 /etc/cron.d/spherex-deploy

echo
echo "SPHEREx is running on http://$(hostname -I | awk '{print $1}')/"
echo "Next: fill $CACHE_DIR (rsync or tools/prepare_demo.py), then point DNS at the droplet."
