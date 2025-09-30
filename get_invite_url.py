#!/usr/bin/env python3

import json
import os
from dotenv import load_dotenv

load_dotenv()

# Get bot info from config
with open('config.json', 'r') as f:
    config = json.load(f)

# Bot client ID should be in your Discord Developer Portal
print("To fix the 'Unknown Integration' error, you need to:")
print("1. Go to https://discord.com/developers/applications")
print("2. Select your bot application")
print("3. Go to OAuth2 > URL Generator")
print("4. Select scopes: 'bot' AND 'applications.commands'")
print("5. Select bot permissions you need (Send Messages, Use Slash Commands, etc.)")
print("6. Use the generated URL to re-invite your bot")
print()
print("The URL should look like:")
print("https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_CLIENT_ID&permissions=YOUR_PERMISSIONS&scope=bot%20applications.commands")
print()
print("Make sure 'applications.commands' is included in the scope!")