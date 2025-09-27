# booking_bot/notifications/service.py - Сервис уведомлений

import logging
from django.utils import timezone
from datetime import timedelta
from typing import Optional, Dict, List
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

User = get_user_model()


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

        # Определяем каналы отправки
        if not channels:
            # Автоматически выбираем доступные каналы для пользователя
            channels = cls._get_user_channels(user)

        notifications = []

        for channel in channels:
            try:
                # Ищем шаблон
                template = NotificationTemplate.objects.get(
                    event=event, channel=channel, is_active=True
                )

                # Определяем получателей
                recipients = cls._get_recipients(template, user, context)

                for recipient in recipients:
                    # Рендерим сообщение
                    language = recipient.get("language", "ru")
                    message = template.render(context, language)

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
                        context=context,
                        scheduled_for=scheduled_for,
                        metadata=kwargs,
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
                role__in=["admin", "super_admin"]
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
