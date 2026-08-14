#!/bin/bash
# Auto-deployment script for folklore Discord bot

set -e

DEPLOY_DIR="/home/stellarhopper/folklore"
REPO_URL="https://github.com/stellarhopper/folklore.git"
LOG_FILE="/var/log/folklore-bot/deploy.log"

echo "[$(date)] Starting deployment..." | tee -a "$LOG_FILE"

# Clone repo if it doesn't exist, otherwise pull
if [ ! -d "$DEPLOY_DIR" ]; then
    echo "[$(date)] Cloning repository..." | tee -a "$LOG_FILE"
    git clone "$REPO_URL" "$DEPLOY_DIR"
else
    echo "[$(date)] Pulling latest changes..." | tee -a "$LOG_FILE"
    cd "$DEPLOY_DIR"
    git fetch origin
    git reset --hard origin/main
fi

cd "$DEPLOY_DIR"

# Install/update dependencies
echo "[$(date)] Installing dependencies..." | tee -a "$LOG_FILE"
pip3 install --user --break-system-packages -r requirements.txt 2>/dev/null || \
    pip3 install --user -r requirements.txt

# Sync systemd units that have drifted from the repo.
# Without this, unit file changes land in git but never reach /etc.
echo "[$(date)] Checking systemd units..." | tee -a "$LOG_FILE"
units_changed=0
mqtt_unit_changed=0

for unit in folklore-bot.service mqtt-deployer.service; do
    src="$DEPLOY_DIR/deploy/$unit"
    dst="/etc/systemd/system/$unit"

    if [ ! -f "$src" ]; then
        continue
    fi

    if cmp -s "$src" "$dst"; then
        continue
    fi

    echo "[$(date)] Updating $unit" | tee -a "$LOG_FILE"
    sudo install -m 644 -o root -g root "$src" "$dst"
    units_changed=1
    if [ "$unit" = "mqtt-deployer.service" ]; then
        mqtt_unit_changed=1
    fi
done

if [ "$units_changed" -eq 1 ]; then
    echo "[$(date)] Reloading systemd..." | tee -a "$LOG_FILE"
    sudo systemctl daemon-reload
else
    echo "[$(date)] Units already up to date" | tee -a "$LOG_FILE"
fi

# Restart the service
echo "[$(date)] Restarting bot service..." | tee -a "$LOG_FILE"
sudo systemctl restart folklore-bot

# mqtt-deployer is deliberately not restarted here: this script runs inside
# that service's cgroup, and KillMode=control-group means restarting it would
# kill this deployment mid-run.
if [ "$mqtt_unit_changed" -eq 1 ]; then
    {
        echo "[$(date)] NOTE: mqtt-deployer.service changed and was installed,"
        echo "[$(date)]   but is still running the previous unit. Apply it with:"
        echo "[$(date)]     sudo systemctl restart mqtt-deployer"
    } | tee -a "$LOG_FILE"
fi

echo "[$(date)] Deployment complete!" | tee -a "$LOG_FILE"

# Show service status
sudo systemctl status folklore-bot --no-pager | tee -a "$LOG_FILE"