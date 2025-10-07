#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from src.discord_bot import KernelBot

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from config.json and environment"""
    # Load environment variables
    load_dotenv()

    config_path = Path(__file__).parent / 'config.json'

    if not config_path.exists():
        logger.error("config.json not found!")
        sys.exit(1)

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Override token from environment
        discord_token = os.getenv('DISCORD_TOKEN')
        if not discord_token:
            logger.error("Discord token not found! Please set DISCORD_TOKEN environment variable")
            sys.exit(1)

        config['discord']['token'] = discord_token


        # Validate required config
        subscriptions = config.get('discord', {}).get('subscriptions', [])
        if not subscriptions:
            logger.error("No Discord subscriptions configured! Please set discord.subscriptions in config.json")
            sys.exit(1)

        # Validate subscription format
        for sub in subscriptions:
            if 'guild_id' not in sub or 'channel' not in sub or 'subsystems' not in sub:
                logger.error("Invalid subscription format! Each subscription needs guild_id, channel, and subsystems")
                sys.exit(1)

        return config

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config.json: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

async def main():
    """Main entry point"""
    logger.info("Starting Linux Kernel Discord Bot...")

    # Load configuration
    config = load_config()

    # Create and run bot
    bot = KernelBot(config)

    try:
        await bot.start(config['discord']['token'])
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)