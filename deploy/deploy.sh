#!/usr/bin/env bash
# Pull the production branch and restart the demo.
# Run as root (the cron entry does this) or with sudo.
set -euo pipefail

BRANCH="${BRANCH:-production}"
APP_DIR="${APP_DIR:-/srv/spherex}"
SERVICE="${SERVICE:-spherex}"

if [ ! -d "$APP_DIR/.git" ]; then
    echo "error: $APP_DIR is not a git checkout" >&2
    exit 1
fi

cd "$APP_DIR"

as_app() {
    if [ "$(id -un)" = "spherex" ]; then
        "$@"
    else
        sudo -H -u spherex "$@"
    fi
}

old_head=$(as_app git rev-parse HEAD)
old_requirements=$(sha256sum requirements.txt | awk '{print $1}')

as_app git fetch --quiet origin "$BRANCH"
as_app git reset --hard --quiet "origin/$BRANCH"

new_head=$(as_app git rev-parse HEAD)
new_requirements=$(sha256sum requirements.txt | awk '{print $1}')

if [ "$old_head" = "$new_head" ] && [ "$old_requirements" = "$new_requirements" ]; then
    echo "already up to date at $new_head"
    exit 0
fi

if [ "$old_requirements" != "$new_requirements" ]; then
    echo "requirements.txt changed; installing"
    as_app "$APP_DIR/.venv/bin/pip" install --quiet -r requirements.txt
fi

if [ "$(id -u)" -eq 0 ]; then
    systemctl restart "$SERVICE"
    systemctl is-active --quiet "$SERVICE"
else
    sudo systemctl restart "$SERVICE"
    sudo systemctl is-active --quiet "$SERVICE"
fi

echo "deployed $(as_app git rev-parse --short HEAD) on $BRANCH"
