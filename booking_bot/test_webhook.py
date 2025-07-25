# test_webhook.py - тест вашего webhook

import requests
import json

NGROK_URL = "https://c1dae9e5294a.ngrok-free.app"
WEBHOOK_URL = f"{NGROK_URL}/telegram/webhook/"

# Тестовое сообщение от Telegram
test_message = {
    "update_id": 123456789,
    "message": {
        "message_id": 1,
        "from": {
            "id": 1016528941,
            "is_bot": False,
            "first_name": "Test",
            "last_name": "User"
        },
        "chat": {
            "id": 1016528941,
            "first_name": "Test",
            "last_name": "User",
            "type": "private"
        },
        "date": 1640995200,
        "text": "/start"
    }
}


def test_webhook():
    print(f"Testing webhook: {WEBHOOK_URL}")

    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'TelegramBot (like TwitterBot)'
    }

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=test_message,
            headers=headers,
            timeout=10
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            print("✅ Webhook работает!")
        else:
            print("❌ Ошибка в webhook")

    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")


def test_direct_access():
    """Проверяем прямой доступ к webhook"""
    try:
        response = requests.get(WEBHOOK_URL, timeout=5)
        print(f"GET request status: {response.status_code}")
        print(f"GET response: {response.text}")
    except Exception as e:
        print(f"GET request error: {e}")


if __name__ == "__main__":
    print("=== Тестирование webhook ===")
    print("1. Проверка GET запроса...")
    test_direct_access()

    print("\n2. Проверка POST запроса...")
    test_webhook()