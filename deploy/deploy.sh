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
pip3 install --user -r requirements.txt

# Restart the service
echo "[$(date)] Restarting bot service..." | tee -a "$LOG_FILE"
sudo systemctl restart folklore-bot

echo "[$(date)] Deployment complete!" | tee -a "$LOG_FILE"

# Show service status
sudo systemctl status folklore-bot --no-pager | tee -a "$LOG_FILE"