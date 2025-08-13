# update_webhook.py - создайте этот файл в корне проекта

"""
Utility script to update and check the Telegram webhook for this bot.

This script reads credentials and domain settings from environment variables.
It replaces the previous hard‑coded ngrok URL and token with a more secure
approach. Set TELEGRAM_BOT_TOKEN and DJANGO_DOMAIN in your environment
before running.
"""
import os
import requests

# Read the bot token and domain from environment variables instead of hard‑coding.
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DOMAIN = os.environ.get("DJANGO_DOMAIN", "https://example.com")

if not BOT_TOKEN:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set in environment variables")

WEBHOOK_URL = f"{DOMAIN}/telegram/webhook/"


def set_webhook():
    """Set Telegram webhook to the configured domain."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    data = {"url": WEBHOOK_URL}
    response = requests.post(url, json=data)
    print(f"Setting webhook to: {WEBHOOK_URL}")
    print(f"Response: {response.json()}")


def get_webhook_info():
    """Get current Telegram webhook information."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    response = requests.get(url)
    print(f"Current webhook info: {response.json()}")


if __name__ == "__main__":
    print("Updating Telegram webhook...")
    set_webhook()
    print("\nChecking webhook info...")
    get_webhook_info()

# Запустите: python update_webhook.py
