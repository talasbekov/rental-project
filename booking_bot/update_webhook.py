# update_webhook.py - создайте этот файл в корне проекта

import requests

# Ваш токен бота
BOT_TOKEN = "7302267102:AAGTSKRPiGWNweB-8-E1sAS6ls-UINwP4is"

# Ваш ngrok URL (замените на актуальный!)
NGROK_URL = "https://e3ff-46-34-194-76.ngrok-free.app"  # получите из ngrok

# URL webhook
WEBHOOK_URL = f"{NGROK_URL}/telegram/webhook/"


def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    data = {"url": WEBHOOK_URL}

    response = requests.post(url, json=data)
    print(f"Setting webhook to: {WEBHOOK_URL}")
    print(f"Response: {response.json()}")


def get_webhook_info():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    response = requests.get(url)
    print(f"Current webhook info: {response.json()}")


if __name__ == "__main__":
    print("Updating Telegram webhook...")
    set_webhook()
    print("\nChecking webhook info...")
    get_webhook_info()

# Запустите: python update_webhook.py