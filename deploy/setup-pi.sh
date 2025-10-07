#!/bin/bash
# Setup script for Raspberry Pi deployment
# Run this script on your Raspberry Pi as the stellarhopper user

set -e

echo "========================================="
echo "Folklore Bot - Raspberry Pi Setup"
echo "========================================="
echo

# Check if running as root
if [ "$EUID" -eq 0 ]; then
   echo "ERROR: Please run as stellarhopper user, not root"
   echo "The script will ask for sudo password when needed"
   exit 1
fi

# Install dependencies
echo "[1/7] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-paho-mqtt git lei pipx

# Create log directory
echo "[2/7] Creating log directory..."
sudo mkdir -p /var/log/folklore-bot
sudo chown stellarhopper:stellarhopper /var/log/folklore-bot

# Clone or update repository
echo "[3/7] Setting up repository..."
if [ ! -d "/home/stellarhopper/folklore" ]; then
    echo "Cloning repository..."
    cd /home/stellarhopper
    git clone https://github.com/stellarhopper/folklore.git
else
    echo "Repository already exists, pulling latest..."
    cd /home/stellarhopper/folklore
    git pull
fi

# Install bot dependencies
echo "[4/7] Installing bot dependencies..."
cd /home/stellarhopper/folklore
sudo apt-get install -y python3-aiohttp python3-bs4 python3-dotenv
# Note: discord.py not in Debian repos, needs venv or --break-system-packages
pip3 install --user --break-system-packages -r requirements.txt 2>/dev/null || \
    pip3 install --user -r requirements.txt

# Install b4 via pipx (Debian's apt version is too old)
echo "Installing b4 >= 0.13.0 via pipx..."
pipx install b4
echo "✓ Installed b4 $(b4 --version)"

# Setup MQTT credentials
echo "[5/7] Setting up MQTT credentials..."
if [ ! -f "/home/stellarhopper/folklore/deploy/.env.mqtt" ]; then
    read -sp "Enter MQTT password: " mqtt_password
    echo
    echo "MQTT_PASSWORD=$mqtt_password" > /home/stellarhopper/folklore/deploy/.env.mqtt
    chmod 600 /home/stellarhopper/folklore/deploy/.env.mqtt
    echo "✓ Created .env.mqtt with credentials"
else
    echo ".env.mqtt already exists, skipping"
fi

# Make scripts executable
chmod +x /home/stellarhopper/folklore/deploy/deploy.sh
chmod +x /home/stellarhopper/folklore/deploy/mqtt_subscriber.py

# Install systemd services
echo "[6/7] Installing systemd services..."

# Install bot service
sudo cp /home/stellarhopper/folklore/deploy/folklore-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable folklore-bot
echo "✓ Installed folklore-bot.service"

# Install MQTT deployer service
sudo cp /home/stellarhopper/folklore/deploy/mqtt-deployer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mqtt-deployer
echo "✓ Installed mqtt-deployer.service"

# Install sudoers file for deployment
sudo cp /home/stellarhopper/folklore/deploy/folklore-sudoers /etc/sudoers.d/folklore
sudo chmod 440 /etc/sudoers.d/folklore
echo "✓ Installed sudoers configuration"

echo
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo
echo "Next steps:"
echo "1. Make sure your Discord token is in /home/stellarhopper/folklore/.env"
echo "2. Start the bot:       sudo systemctl start folklore-bot"
echo "3. Start the deployer:  sudo systemctl start mqtt-deployer"
echo "4. Check bot status:    sudo systemctl status folklore-bot"
echo "5. Check deployer:      sudo systemctl status mqtt-deployer"
echo "6. View logs:           sudo journalctl -u folklore-bot -f"
echo "7. View deploy logs:    sudo journalctl -u mqtt-deployer -f"
echo
echo "Auto-deployment is now configured!"
echo "Push to GitHub main branch will automatically deploy to this Pi."