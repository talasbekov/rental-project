# auto_ngrok.py - утилита для автоматического получения ngrok URL

import requests
import json
import time
import subprocess
import os


def get_ngrok_url():
    """Получить текущий ngrok URL"""
    try:
        response = requests.get("http://localhost:4040/api/tunnels")
        if response.status_code == 200:
            tunnels = response.json()['tunnels']
            for tunnel in tunnels:
                if tunnel['proto'] == 'https':
                    return tunnel['public_url']
    except:
        pass
    return None


def update_webhook(ngrok_url, bot_token):
    """Обновить webhook Telegram"""
    webhook_url = f"{ngrok_url}/telegram/webhook/"
    api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"

    response = requests.post(api_url, json={"url": webhook_url})
    return response.json()


def main():
    BOT_TOKEN = "7302267102:AAGTSKRPiGWNweB-8-E1sAS6ls-UINwP4is"

    print("Waiting for ngrok to start...")
    time.sleep(3)

    ngrok_url = get_ngrok_url()
    if ngrok_url:
        print(f"Found ngrok URL: {ngrok_url}")

        # Обновляем webhook
        result = update_webhook(ngrok_url, BOT_TOKEN)
        print(f"Webhook updated: {result}")

        # Сохраняем URL в переменную окружения
        os.environ['NGROK_URL'] = ngrok_url

        # Или сохраняем в файл
        with open('.env.ngrok', 'w') as f:
            f.write(f"NGROK_URL={ngrok_url}\n")

        print(f"Add this to your settings.py:")
        print(f"DOMAIN = '{ngrok_url}'")
        print(f"ALLOWED_HOSTS.append('{ngrok_url.replace('https://', '').replace('http://', '')}')")

    else:
        print("ngrok URL not found. Make sure ngrok is running on port 4040")


if __name__ == "__main__":
    main()