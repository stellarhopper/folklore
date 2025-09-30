# Raspberry Pi Deployment Setup

Automatic deployment system using MQTT for the Folklore Discord bot.

## Architecture

```
GitHub Push → GitHub Actions → MQTT Broker (HiveMQ) → Raspberry Pi → Deploy
```

**No ports open on your Pi!** The Pi connects outbound to HiveMQ Cloud.

## Setup on Raspberry Pi

1. **Run the setup script:**
   ```bash
   bash deploy/setup-pi.sh
   ```
   This will:
   - Install dependencies (Python, MQTT client)
   - Clone/update the repository
   - Create log directories
   - Install systemd services
   - Prompt for MQTT password

2. **Add your Discord token:**
   ```bash
   echo "DISCORD_TOKEN=your_token_here" > /home/stellarhopper/folklore/.env
   ```

3. **Start the services:**
   ```bash
   sudo systemctl start folklore-bot
   sudo systemctl start mqtt-deployer
   ```

4. **Check status:**
   ```bash
   sudo systemctl status folklore-bot
   sudo systemctl status mqtt-deployer
   ```

## Setup on GitHub

Add the MQTT password as a GitHub secret:

1. Go to your repo → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `MQTT_PASSWORD`
4. Value: `Ab5bvLqpxacxwbB`
5. Click "Add secret"

## How it Works

### On Boot
- `folklore-bot.service` starts the Discord bot automatically
- `mqtt-deployer.service` connects to HiveMQ and listens for deployment messages

### On Git Push
1. You push to `main` branch
2. GitHub Actions workflow triggers
3. Workflow publishes "deploy" message to MQTT topic `folklore/deploy`
4. Pi's MQTT subscriber receives the message
5. Pi runs `deploy/deploy.sh`:
   - Pulls latest code
   - Installs dependencies
   - Restarts the bot
6. Bot automatically runs with new code

## Manual Operations

### View Logs
```bash
# Bot logs
sudo journalctl -u folklore-bot -f

# Deployment logs
sudo journalctl -u mqtt-deployer -f

# Or raw log files
tail -f /var/log/folklore-bot/output.log
tail -f /var/log/folklore-bot/error.log
tail -f /var/log/folklore-bot/mqtt-deployer.log
tail -f /var/log/folklore-bot/deploy.log
```

### Manual Deployment
```bash
bash /home/stellarhopper/folklore/deploy/deploy.sh
```

### Restart Services
```bash
sudo systemctl restart folklore-bot
sudo systemctl restart mqtt-deployer
```

### Stop Services
```bash
sudo systemctl stop folklore-bot
sudo systemctl stop mqtt-deployer
```

## Files

- `folklore-bot.service` - Systemd service for the Discord bot
- `mqtt-deployer.service` - Systemd service for MQTT deployment listener
- `mqtt_subscriber.py` - Python script that listens for MQTT deploy messages
- `deploy.sh` - Deployment script (git pull, install deps, restart)
- `setup-pi.sh` - One-time setup script for the Pi
- `.env.mqtt` - MQTT credentials (not in git)

## Security

- MQTT password stored in `.env.mqtt` (600 permissions, not in git)
- Discord token stored in `.env` (not in git)
- HiveMQ uses TLS encryption (port 8883)
- No inbound ports required on Raspberry Pi
- Services run as non-root user `stellarhopper`

## Troubleshooting

### Bot won't start
Check if Discord token is set:
```bash
cat /home/stellarhopper/folklore/.env
```

### MQTT deployer won't connect
Check credentials:
```bash
cat /home/stellarhopper/folklore/deploy/.env.mqtt
```

Test MQTT connection:
```bash
python3 /home/stellarhopper/folklore/deploy/mqtt_subscriber.py
```

### Deployment not triggering
Check GitHub Actions workflow ran successfully:
- Go to your repo → Actions tab
- Check the "Deploy to Raspberry Pi" workflow

Manually trigger a deployment for testing:
```bash
# From any machine with mosquitto-clients installed
mosquitto_pub \
  -h 7bc60cfe8a37497d8f627acb66ce353c.s1.eu.hivemq.cloud \
  -p 8883 \
  -t "folklore/deploy" \
  -m "deploy" \
  -u "folklore-mqtt" \
  -P "Ab5bvLqpxacxwbB" \
  --capath /etc/ssl/certs/
```