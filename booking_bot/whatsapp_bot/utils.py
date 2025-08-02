import re
import requests
import logging
import json
from django.conf import settings
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# WhatsApp Cloud API endpoint
WHATSAPP_API_URL = f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_NUMBER_ID}"
WHATSAPP_TOKEN = settings.WHATSAPP_ACCESS_TOKEN


def escape_markdown(text: str) -> str:
    """Экранирует символы для WhatsApp"""
    # WhatsApp использует другой формат markdown
    return text.replace('*', '\\*').replace('_', '\\_')


def send_whatsapp_message(phone_number: str, text: str, preview_url: bool = False):
    """Отправить текстовое сообщение через WhatsApp Business API"""
    url = f"{WHATSAPP_API_URL}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "text",
        "text": {
            "preview_url": preview_url,
            "body": text
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {phone_number}: {e}")
        return None


def send_whatsapp_button_message(
        phone_number: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        header: Optional[str] = None,
        footer: Optional[str] = None
):
    """Отправить сообщение с кнопками (interactive message)"""
    url = f"{WHATSAPP_API_URL}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    # Формируем interactive message
    interactive = {
        "type": "button",
        "body": {"text": body_text}
    }

    if header:
        interactive["header"] = {"type": "text", "text": header}

    if footer:
        interactive["footer"] = {"text": footer}

    # Добавляем кнопки (максимум 3 кнопки в WhatsApp)
    interactive["action"] = {
        "buttons": [
            {
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"][:20]  # Максимум 20 символов
                }
            }
            for btn in buttons[:3]  # Берем только первые 3 кнопки
        ]
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "interactive",
        "interactive": interactive
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending WhatsApp button message to {phone_number}: {e}")
        return None


def send_whatsapp_list_message(
        phone_number: str,
        body_text: str,
        button_text: str,
        sections: List[Dict],
        header: Optional[str] = None,
        footer: Optional[str] = None
):
    """Отправить сообщение со списком выбора (для больших меню)"""
    url = f"{WHATSAPP_API_URL}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    interactive = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": button_text[:20],  # Максимум 20 символов
            "sections": sections
        }
    }

    if header:
        interactive["header"] = {"type": "text", "text": header}

    if footer:
        interactive["footer"] = {"text": footer}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "interactive",
        "interactive": interactive
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending WhatsApp list message to {phone_number}: {e}")
        return None


def send_whatsapp_image(
        phone_number: str,
        image_url: str,
        caption: Optional[str] = None
):
    """Отправить изображение через WhatsApp"""
    url = f"{WHATSAPP_API_URL}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    image_data = {"link": image_url}
    if caption:
        image_data["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "image",
        "image": image_data
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending WhatsApp image to {phone_number}: {e}")
        return None


def send_whatsapp_media_group(
        phone_number: str,
        image_urls: List[str],
        caption: Optional[str] = None
):
    """Отправить группу изображений (поочередно, т.к. WhatsApp не поддерживает группы)"""
    if not image_urls:
        return None

    results = []

    # Отправляем первое изображение с подписью
    first_result = send_whatsapp_image(phone_number, image_urls[0], caption)
    results.append(first_result)

    # Остальные изображения без подписи
    for image_url in image_urls[1:]:
        result = send_whatsapp_image(phone_number, image_url)
        results.append(result)

    return results


def send_whatsapp_location(
        phone_number: str,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
        address: Optional[str] = None
):
    """Отправить локацию через WhatsApp"""
    url = f"{WHATSAPP_API_URL}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    location_data = {
        "latitude": latitude,
        "longitude": longitude
    }

    if name:
        location_data["name"] = name
    if address:
        location_data["address"] = address

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "location",
        "location": location_data
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending WhatsApp location to {phone_number}: {e}")
        return None


def send_whatsapp_document(
        phone_number: str,
        document_url: str,
        filename: Optional[str] = None,
        caption: Optional[str] = None
):
    """Отправить документ через WhatsApp"""
    url = f"{WHATSAPP_API_URL}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    document_data = {"link": document_url}
    if filename:
        document_data["filename"] = filename
    if caption:
        document_data["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "document",
        "document": document_data
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending WhatsApp document to {phone_number}: {e}")
        return None


def mark_message_as_read(message_id: str):
    """Отметить сообщение как прочитанное"""
    url = f"{WHATSAPP_API_URL}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error marking message as read: {e}")
        return None


def get_media_url(media_id: str) -> Optional[str]:
    """Получить URL медиафайла по его ID"""
    url = f"https://graph.facebook.com/v18.0/{media_id}"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("url")
    except Exception as e:
        logger.error(f"Error getting media URL for {media_id}: {e}")
        return None


def download_media(media_url: str, media_id: str) -> Optional[bytes]:
    """Скачать медиафайл с WhatsApp серверов"""
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
    }

    try:
        response = requests.get(media_url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"Error downloading media {media_id}: {e}")
        return None
