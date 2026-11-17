#!/bin/sh
set -eu
mkdir -p "${NEWS_IMAGE_DIR:-/var/lib/parlor/news}"
chown appuser:appuser "${NEWS_IMAGE_DIR:-/var/lib/parlor/news}"
cd /app
exec setpriv --reuid=appuser --regid=appuser --init-groups \
    env HOME=/home/appuser USER=appuser LOGNAME=appuser \
    python -m scripts.serve
