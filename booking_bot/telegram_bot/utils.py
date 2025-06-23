import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

BOT_URL = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


def send_telegram_message(chat_id, text, reply_markup=None):
    """Send a text message via Telegram Bot API"""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        response = requests.post(f"{BOT_URL}/sendMessage", json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")
        return None


def _edit_message(chat_id, message_id, text, reply_markup=None):
    """Edit an existing message"""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        response = requests.post(f"{BOT_URL}/editMessageText", json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error editing message {message_id} in chat {chat_id}: {e}")
        return None


def send_photo(chat_id, photo_url, caption=None, reply_markup=None):
    """Send a photo via Telegram Bot API"""
    payload = {
        "chat_id": chat_id,
        "photo": photo_url
    }
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "Markdown"
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        response = requests.post(f"{BOT_URL}/sendPhoto", json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending photo to {chat_id}: {e}")
        return None


def send_photo_group(chat_id, photo_urls, caption=None):
    """Send multiple photos as a media group"""
    if not photo_urls:
        return None

    media = []
    for i, url in enumerate(photo_urls[:10]):  # Telegram limit is 10 photos
        media_item = {
            "type": "photo",
            "media": url
        }
        # Add caption only to the first photo
        if i == 0 and caption:
            media_item["caption"] = caption
            media_item["parse_mode"] = "Markdown"
        media.append(media_item)

    payload = {
        "chat_id": chat_id,
        "media": media
    }

    try:
        response = requests.post(f"{BOT_URL}/sendMediaGroup", json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending photo group to {chat_id}: {e}")
        return None


def send_document(chat_id, document_url, caption=None, filename=None):
    """Send a document via Telegram Bot API"""
    payload = {
        "chat_id": chat_id,
        "document": document_url
    }
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "Markdown"
    if filename:
        payload["filename"] = filename

    try:
        response = requests.post(f"{BOT_URL}/sendDocument", json=payload, timeout=20)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error sending document to {chat_id}: {e}")
        return None


def answer_callback_query(callback_query_id, text=None, show_alert=False):
    """Answer a callback query (remove loading state from inline button)"""
    payload = {
        "callback_query_id": callback_query_id
    }
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert

    try:
        response = requests.post(f"{BOT_URL}/answerCallbackQuery", json=payload, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error answering callback query {callback_query_id}: {e}")
        return None


def delete_message(chat_id, message_id):
    """Delete a message"""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id
    }

    try:
        response = requests.post(f"{BOT_URL}/deleteMessage", json=payload, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error deleting message {message_id} in chat {chat_id}: {e}")
        return None


def get_file_url(file_id):
    """Get download URL for a file uploaded to Telegram"""
    try:
        response = requests.get(f"{BOT_URL}/getFile", params={"file_id": file_id}, timeout=10)
        response.raise_for_status()
        result = response.json()

        if result.get("ok") and result.get("result"):
            file_path = result["result"].get("file_path")
            if file_path:
                return f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}"
    except Exception as e:
        logger.error(f"Error getting file URL for {file_id}: {e}")

    return None


def set_chat_menu_button(chat_id):
    """Set menu button for the chat"""
    payload = {
        "chat_id": chat_id,
        "menu_button": {
            "type": "commands"
        }
    }

    try:
        response = requests.post(f"{BOT_URL}/setChatMenuButton", json=payload, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error setting menu button for chat {chat_id}: {e}")
        return None