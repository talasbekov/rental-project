import requests
from django.conf import settings

BOT_URL = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

def send_telegram_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{BOT_URL}/sendMessage", json=payload, timeout=5).raise_for_status()

def _edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{BOT_URL}/editMessageText", json=payload, timeout=5).raise_for_status()
