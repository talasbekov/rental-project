#!/usr/bin/env python
"""Script to setup Telegram bot webhook."""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

import django
django.setup()

from telegram import Bot
from telegram.error import TelegramError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_webhook_info(bot: Bot):
    """Get current webhook information."""
    try:
        info = await bot.get_webhook_info()
        logger.info(f"Current webhook URL: {info.url}")
        logger.info(f"Pending updates: {info.pending_update_count}")
        logger.info(f"Last error: {info.last_error_message}")
        logger.info(f"Last error date: {info.last_error_date}")
        logger.info(f"Max connections: {info.max_connections}")
        logger.info(f"Allowed updates: {info.allowed_updates}")
        return info
    except TelegramError as e:
        logger.error(f"Error getting webhook info: {e}")
        return None


async def set_webhook(bot: Bot, webhook_url: str, secret_token: str | None = None):
    """Set webhook URL for the bot."""
    try:
        # Delete existing webhook first
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Deleted existing webhook")

        # Set new webhook
        result = await bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=False,
            secret_token=secret_token,
        )

        if result:
            logger.info(f"✅ Webhook successfully set to: {webhook_url}")
            # Verify webhook is set
            info = await get_webhook_info(bot)
            return True
        else:
            logger.error("❌ Failed to set webhook")
            return False

    except TelegramError as e:
        logger.error(f"❌ Error setting webhook: {e}")
        return False


async def delete_webhook(bot: Bot):
    """Delete webhook (switch back to polling)."""
    try:
        result = await bot.delete_webhook(drop_pending_updates=False)
        if result:
            logger.info("✅ Webhook deleted successfully")
            return True
        else:
            logger.error("❌ Failed to delete webhook")
            return False
    except TelegramError as e:
        logger.error(f"❌ Error deleting webhook: {e}")
        return False


async def get_ngrok_url():
    """Get ngrok public URL from ngrok API."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:4040/api/tunnels")
            data = response.json()

            for tunnel in data.get("tunnels", []):
                if tunnel.get("proto") == "https":
                    return tunnel.get("public_url")

        return None
    except Exception as e:
        logger.error(f"Error getting ngrok URL: {e}")
        return None


async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage Telegram bot webhook")
    parser.add_argument(
        "action",
        choices=["set", "delete", "info", "auto"],
        help="Action to perform"
    )
    parser.add_argument(
        "--url",
        help="Webhook URL (required for 'set' action)"
    )
    parser.add_argument(
        "--token",
        help="Secret token for webhook validation"
    )
    parser.add_argument(
        "--auto-ngrok",
        action="store_true",
        help="Automatically detect ngrok URL"
    )

    args = parser.parse_args()

    # Get bot token from environment
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not found in environment")
        sys.exit(1)

    bot = Bot(token=bot_token)

    if args.action == "info":
        await get_webhook_info(bot)

    elif args.action == "delete":
        await delete_webhook(bot)

    elif args.action == "set":
        webhook_url = args.url

        if args.auto_ngrok or not webhook_url:
            logger.info("Trying to get ngrok URL...")
            ngrok_url = await get_ngrok_url()
            if ngrok_url:
                webhook_url = f"{ngrok_url}/telegram/webhook/"
                logger.info(f"Detected ngrok URL: {webhook_url}")
            elif not webhook_url:
                logger.error("❌ No webhook URL provided and ngrok URL not found")
                sys.exit(1)

        if not webhook_url:
            logger.error("❌ Webhook URL is required")
            sys.exit(1)

        await set_webhook(bot, webhook_url, args.token)

    elif args.action == "auto":
        logger.info("🤖 Auto-setup mode: detecting ngrok and setting webhook...")

        ngrok_url = await get_ngrok_url()
        if not ngrok_url:
            logger.error("❌ ngrok not running or URL not found")
            logger.info("💡 Start ngrok with: ngrok http 8000")
            sys.exit(1)

        webhook_url = f"{ngrok_url}/telegram/webhook/"
        secret_token = os.environ.get("WEBHOOK_SECRET")

        logger.info(f"🔗 ngrok URL: {ngrok_url}")
        logger.info(f"📍 Webhook URL: {webhook_url}")

        success = await set_webhook(bot, webhook_url, secret_token)

        if success:
            logger.info("\n" + "="*60)
            logger.info("✅ Telegram Bot Webhook Setup Complete!")
            logger.info("="*60)
            logger.info(f"Webhook URL: {webhook_url}")
            logger.info(f"ngrok URL: {ngrok_url}")
            logger.info("\n🎯 Now you can test your bot by sending messages!")
            logger.info("="*60)
        else:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
