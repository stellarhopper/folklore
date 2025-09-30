#!/usr/bin/env python3
"""
MQTT subscriber for folklore bot deployment
Listens for deployment messages from GitHub Actions
"""

import os
import subprocess
import sys
import time
import ssl
import paho.mqtt.client as mqtt

# MQTT Configuration
MQTT_BROKER = os.environ.get('MQTT_BROKER', '7bc60cfe8a37497d8f627acb66ce353c.s1.eu.hivemq.cloud')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '8883'))
MQTT_USERNAME = os.environ.get('MQTT_USERNAME', 'folklore-mqtt')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD')
MQTT_TOPIC = 'folklore/deploy'

DEPLOY_SCRIPT = '/home/stellarhopper/folklore/deploy/deploy.sh'


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker"""
    if rc == 0:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connected to MQTT broker")
        client.subscribe(MQTT_TOPIC)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Subscribed to {MQTT_TOPIC}")
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connection failed with code {rc}")


def on_message(client, userdata, msg):
    """Callback when message received"""
    payload = msg.payload.decode()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Received message: {payload}")

    if payload == 'deploy':
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Triggering deployment...")

        try:
            result = subprocess.run(
                ['bash', DEPLOY_SCRIPT],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Deployment successful!")
                print(result.stdout)
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Deployment failed!")
                print(result.stderr)
        except subprocess.TimeoutExpired:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Deployment timed out!")
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error during deployment: {e}")
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Unknown command: {payload}")


def on_disconnect(client, userdata, rc):
    """Callback when disconnected"""
    if rc != 0:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Unexpected disconnect (code {rc}), reconnecting...")


def main():
    """Main function"""
    if not MQTT_PASSWORD:
        print("ERROR: MQTT_PASSWORD environment variable not set!")
        sys.exit(1)

    # Create MQTT client
    client = mqtt.Client(client_id="folklore-pi-subscriber")
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # Enable TLS
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)

    # Set callbacks
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    # Connect to broker
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Shutting down...")
        client.disconnect()
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()