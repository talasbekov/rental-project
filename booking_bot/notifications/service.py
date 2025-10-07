# booking_bot/notifications/service.py - Сервис уведомлений

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

User = get_user_model()


DEFAULT_TEMPLATES = {
    "low_occupancy": [
        {
            "channel": "telegram",
            "template_ru": (
                "📉 Низкая загрузка по объекту {property_name}.\n"
                "За последние 30 дней занятость составила {occupancy_rate:.0f}%.\n"
                "{recommendation}"
            ),
            "template_kz": (
                "📉 {property_name} объектісінің жүктемесі төмен.\n"
                "Соңғы 30 күн ішінде жүктемесі {occupancy_rate:.0f}% болды.\n"
                "{recommendation}"
            ),
            "template_en": (
                "📉 Low occupancy detected for {property_name}.\n"
                "Occupancy in the last 30 days was {occupancy_rate:.0f}%.\n"
                "{recommendation}"
            ),
            "send_to_owner": True,
            "send_to_user": False,
            "send_to_admins": False,
        }
    ],
    "update_photos_needed": [
        {
            "channel": "telegram",
            "template_ru": (
                "📷 Обновите фотографии для {property_name}.\n"
                "Сейчас загружено только {photo_count} шт.\n"
                "{recommendation}"
            ),
            "template_kz": (
                "📷 {property_name} үшін фотоларды жаңартыңыз.\n"
                "Қазір {photo_count} фото бар.\n"
                "{recommendation}"
            ),
            "template_en": (
                "📷 Please refresh photos for {property_name}.\n"
                "Only {photo_count} images uploaded.\n"
                "{recommendation}"
            ),
            "send_to_owner": True,
            "send_to_user": False,
            "send_to_admins": False,
        }
    ],
    "update_price_needed": [
        {
            "channel": "telegram",
            "template_ru": (
                "💸 Пересмотрите цену для {property_name}.\n"
                "Текущая цена: {current_price:.0f} ₸, средняя по району: {avg_price:.0f} ₸.\n"
                "{recommendation}"
            ),
            "template_kz": (
                "💸 {property_name} үшін бағаны қайта қараңыз.\n"
                "Ағымдағы баға: {current_price:.0f} ₸, аудан бойынша орташа: {avg_price:.0f} ₸.\n"
                "{recommendation}"
            ),
            "template_en": (
                "💸 Review the price for {property_name}.\n"
                "Current price: {current_price:.0f} ₸, district average: {avg_price:.0f} ₸.\n"
                "{recommendation}"
            ),
            "send_to_owner": True,
            "send_to_user": False,
            "send_to_admins": False,
        }
    ],
    "high_ko_factor": [
        {
            "channel": "telegram",
            "template_ru": (
                "⚠️ Высокий KO-фактор у гостя {guest_username}: {ko_factor_percent:.0f}%\n"
                "Всего броней: {total_bookings}, отмен: {cancelled_bookings}."
            ),
            "template_kz": (
                "⚠️ Қонақ {guest_username} үшін KO коэффициенті жоғары: {ko_factor_percent:.0f}%\n"
                "Барлық броньдар: {total_bookings}, болдырмаулар: {cancelled_bookings}."
            ),
            "template_en": (
                "⚠️ Guest {guest_username} has a high KO-factor: {ko_factor_percent:.0f}%\n"
                "Total bookings: {total_bookings}, cancellations: {cancelled_bookings}."
            ),
            "send_to_owner": False,
            "send_to_user": False,
            "send_to_admins": True,
        }
    ],
}


class NotificationService:
    """Централизованный сервис для отправки уведомлений"""

    @classmethod
    def schedule(
        cls,
        event: str,
        user: Optional[User] = None,
        context: Dict = None,
        channels: Optional[List[str]] = None,
        delay_minutes: int = 0,
        **kwargs,
    ):
        """Планирование уведомления"""
        from .models import NotificationTemplate, NotificationQueue

        context = context or {}

        notifications = []

        from .models import NotificationTemplate

        cls._ensure_default_templates(event)

        # Определяем каналы отправки
        if not channels:
            channels = cls._get_user_channels(user)

        templates_qs = NotificationTemplate.objects.filter(
            event=event, is_active=True
        )
        templates_by_channel = {tpl.channel: tpl for tpl in templates_qs}

        if not channels:
            channels = list(templates_by_channel.keys())

        if not channels:
            channels = ["telegram"]

        for channel in channels:
            try:
                template = templates_by_channel.get(channel)
                if not template:
                    template = cls._ensure_default_templates(event, channel)
                    if template:
                        templates_by_channel[channel] = template
                    else:
                        logger.warning(
                            "No template available for event '%s' and channel '%s'",
                            event,
                            channel,
                        )
                        continue

                # Определяем получателей
                recipients = cls._get_recipients(template, user, context)

                for recipient in recipients:
                    # Рендерим сообщение
                    language = recipient.get("language", "ru")
                    message = template.render(context, language)

                    serialized_context = cls._prepare_payload(context)
                    serialized_metadata = cls._prepare_payload(kwargs)

                    # Создаем уведомление в очереди
                    scheduled_for = timezone.now() + timedelta(
                        minutes=delay_minutes or template.delay_minutes
                    )

                    notification = NotificationQueue.objects.create(
                        user=recipient.get("user"),
                        phone_number=recipient.get("phone_number", ""),
                        email=recipient.get("email", ""),
                        telegram_chat_id=recipient.get("telegram_chat_id", ""),
                        event=event,
                        channel=channel,
                        message=message,
                        context=serialized_context,
                        scheduled_for=scheduled_for,
                        metadata=serialized_metadata,
                    )

                    notifications.append(notification)

                    logger.info(
                        f"Scheduled {event} notification via {channel} for {scheduled_for}"
                    )

            except NotificationTemplate.DoesNotExist:
                logger.warning(f"No template found for {event} via {channel}")
            except Exception as e:
                logger.error(f"Error scheduling notification: {e}")

        # Запускаем обработку через Celery, если нужно отправить сразу
        if delay_minutes == 0 and notifications:
            try:
                from .tasks import process_notification_queue

                process_notification_queue.delay()
            except Exception as exc:  # noqa: BLE001 - fallback
                logger.warning(
                    "Failed to enqueue notification queue processing: %s", exc
                )
                cls.process_queue()

        return notifications

    @classmethod
    def _get_user_channels(cls, user: User) -> List[str]:
        """Определение доступных каналов для пользователя"""
        channels = []

        if not user or not hasattr(user, "profile"):
            return channels

        profile = user.profile

        if profile.telegram_chat_id:
            channels.append("telegram")

        if profile.whatsapp_phone or profile.phone_number:
            channels.append("whatsapp")
            channels.append("sms")

        if user.email:
            channels.append("email")

        return channels

    @classmethod
    def _get_recipients(cls, template, user, context):
        """Определение получателей уведомления"""
        recipients = []

        # Пользователь
        if template.send_to_user and user:
            recipients.append(
                {
                    "user": user,
                    "phone_number": getattr(user.profile, "phone_number", ""),
                    "telegram_chat_id": getattr(user.profile, "telegram_chat_id", ""),
                    "email": user.email,
                    "language": getattr(user.profile, "language", "ru"),
                }
            )

        # Владелец (если есть в контексте)
        if template.send_to_owner and "property" in context:
            property_obj = context["property"]
            if hasattr(property_obj, "owner"):
                owner = property_obj.owner
                recipients.append(
                    {
                        "user": owner,
                        "phone_number": getattr(owner.profile, "phone_number", ""),
                        "telegram_chat_id": getattr(
                            owner.profile, "telegram_chat_id", ""
                        ),
                        "email": owner.email,
                        "language": getattr(owner.profile, "language", "ru"),
                    }
                )

        # Администраторы
        if template.send_to_admins:
            from booking_bot.users.models import UserProfile

            admins = UserProfile.objects.filter(
                role__in=["admin", "super_admin", "super_user"]
            ).select_related("user")

            for admin_profile in admins:
                recipients.append(
                    {
                        "user": admin_profile.user,
                        "phone_number": admin_profile.phone_number,
                        "telegram_chat_id": admin_profile.telegram_chat_id,
                        "email": admin_profile.user.email,
                        "language": getattr(admin_profile, "language", "ru"),
                    }
                )

        return recipients

    @classmethod
    def _prepare_payload(cls, payload):
        if payload is None:
            return {}
        return cls._make_json_safe(payload)

    @classmethod
    def _ensure_default_templates(cls, event: str, channel: Optional[str] = None):
        from .models import NotificationTemplate

        defaults = DEFAULT_TEMPLATES.get(event, [])
        created_template = None

        for item in defaults:
            if channel and item["channel"] != channel:
                continue

            template, created = NotificationTemplate.objects.get_or_create(
                event=event,
                channel=item["channel"],
                defaults={
                    "template_ru": item["template_ru"],
                    "template_kz": item.get("template_kz", item["template_ru"]),
                    "template_en": item.get("template_en", item["template_ru"]),
                    "send_to_user": item.get("send_to_user", True),
                    "send_to_owner": item.get("send_to_owner", False),
                    "send_to_admins": item.get("send_to_admins", False),
                    "delay_minutes": 0,
                },
            )
            if created:
                logger.info(
                    "Default notification template created for event '%s' (channel %s)",
                    event,
                    item["channel"],
                )
            if channel:
                created_template = template

        return created_template

    @classmethod
    def _make_json_safe(cls, value):
        if isinstance(value, dict):
            return {str(key): cls._make_json_safe(val) for key, val in value.items()}

        if isinstance(value, (list, tuple, set)):
            return [cls._make_json_safe(item) for item in value]

        if isinstance(value, models.Model):
            return {
                "model": value._meta.label_lower,
                "pk": value.pk,
            }

        if isinstance(value, (datetime, date)):
            return value.isoformat()

        if isinstance(value, Decimal):
            return float(value)

        if hasattr(value, "isoformat") and callable(value.isoformat):
            try:
                return value.isoformat()
            except Exception:  # noqa: BLE001 - fallback на строку
                return str(value)

        if isinstance(value, (str, int, float, bool)) or value is None:
            return value

        return str(value)

    @classmethod
    def process_queue(cls):
        """Обработка очереди уведомлений"""
        from .models import NotificationQueue, NotificationLog

        # Получаем уведомления для отправки
        notifications = NotificationQueue.objects.filter(
            status="pending", scheduled_for__lte=timezone.now()
        ).order_by("scheduled_for")[
            :50
        ]  # Batch по 50

        for notification in notifications:
            try:
                notification.status = "processing"
                notification.attempts += 1
                notification.save()

                # Отправляем через соответствующий канал
                sender = cls._get_sender(notification.channel)
                result = sender.send(notification)

                if result["success"]:
                    notification.status = "sent"
                    notification.sent_at = timezone.now()
                else:
                    if notification.attempts >= 3:
                        notification.status = "failed"
                    else:
                        notification.status = "pending"
                        notification.scheduled_for = timezone.now() + timedelta(
                            minutes=5
                        )

                    notification.error_message = result.get("error", "")

                # Логируем
                NotificationLog.objects.create(
                    notification=notification,
                    status=notification.status,
                    message=result.get("message", ""),
                    response=result,
                )

                notification.save()

            except Exception as e:
                logger.error(f"Error processing notification {notification.id}: {e}")

                notification.status = "failed"
                notification.error_message = str(e)
                notification.save()

    @classmethod
    def _get_sender(cls, channel):
        """Получение отправителя для канала"""
        from .senders import TelegramSender, WhatsAppSender, EmailSender, SMSSender

        senders = {
            "telegram": TelegramSender(),
            "whatsapp": WhatsAppSender(),
            "email": EmailSender(),
            "sms": SMSSender(),
        }

        return senders.get(channel)
