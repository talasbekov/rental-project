# booking_bot/notifications/senders.py - Реализации отправителей

from abc import ABC, abstractmethod
from booking_bot.telegram_bot.utils import send_telegram_message
from booking_bot.whatsapp_bot.utils import send_whatsapp_message
import logging

logger = logging.getLogger(__name__)


class BaseSender(ABC):
    """Базовый класс для отправителей"""

    @abstractmethod
    def send(self, notification):
        pass


class TelegramSender(BaseSender):
    """Отправка через Telegram"""

    def send(self, notification):
        try:
            if not notification.telegram_chat_id:
                return {"success": False, "error": "No telegram_chat_id"}

            result = send_telegram_message(
                notification.telegram_chat_id, notification.message
            )

            return {
                "success": bool(result),
                "message": "Sent via Telegram",
                "response": result,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class WhatsAppSender(BaseSender):
    """Отправка через WhatsApp"""

    def send(self, notification):
        try:
            phone = (
                notification.phone_number or notification.user.profile.whatsapp_phone
            )

            if not phone:
                return {"success": False, "error": "No phone number"}

            result = send_whatsapp_message(phone, notification.message)

            return {
                "success": bool(result),
                "message": "Sent via WhatsApp",
                "response": result,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class EmailSender(BaseSender):
    """Отправка через Email"""

    def send(self, notification):
        from django.core.mail import send_mail
        from django.conf import settings

        try:
            if not notification.email:
                return {"success": False, "error": "No email"}

            send_mail(
                subject=notification.context.get("subject", "ЖильеGO"),
                message=notification.message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.email],
                fail_silently=False,
            )

            return {"success": True, "message": "Sent via Email"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class SMSSender(BaseSender):
    """Отправка через SMS"""

    def send(self, notification):
        # Интеграция с SMS провайдером (Twilio, Mobizon и т.д.)
        return {"success": False, "error": "SMS not implemented"}
