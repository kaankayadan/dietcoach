#!/bin/bash
# Fleet Tracker — VPS deploy script
# Cron: 0 7 * * * /opt/dietcoach/fleet-tracker/deploy.sh >> /var/log/fleet-tracker.log 2>&1

set -e

REPO_DIR="/opt/dietcoach"
FLEET_DIR="$REPO_DIR/fleet-tracker"

echo "=== Deploy başladı: $(date) ==="

cd "$REPO_DIR"
git pull origin main

cd "$FLEET_DIR"
docker compose build --no-cache
docker compose up -d

echo "=== Deploy tamamlandı: $(date) ==="
