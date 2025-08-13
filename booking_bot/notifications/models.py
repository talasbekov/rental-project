# booking_bot/notifications/models.py - Модели для системы уведомлений

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class NotificationTemplate(models.Model):
    """Шаблоны уведомлений"""

    EVENT_CHOICES = [
        ("booking_created", "Новое бронирование"),
        ("booking_confirmed", "Бронирование подтверждено"),
        ("booking_cancelled", "Бронирование отменено"),
        ("payment_success", "Успешная оплата"),
        ("payment_failed", "Ошибка оплаты"),
        ("checkin_reminder", "Напоминание о заезде"),
        ("checkout_reminder", "Напоминание о выезде"),
        ("review_request", "Запрос отзыва"),
        ("property_added", "Квартира добавлена"),
        ("low_occupancy", "Низкая загрузка"),
        ("cleaning_needed", "Требуется уборка"),
        ("maintenance_alert", "Требуется обслуживание"),
    ]

    CHANNEL_CHOICES = [
        ("telegram", "Telegram"),
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
        ("sms", "SMS"),
        ("push", "Push уведомление"),
    ]

    event = models.CharField(max_length=50, choices=EVENT_CHOICES, unique=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)

    # Шаблоны для разных языков
    template_ru = models.TextField(help_text="Используйте {переменные} для подстановки")
    template_kz = models.TextField(blank=True, help_text="Казахский вариант")
    template_en = models.TextField(blank=True, help_text="Английский вариант")

    # Настройки
    is_active = models.BooleanField(default=True)
    delay_minutes = models.IntegerField(
        default=0, help_text="Задержка перед отправкой (минуты)"
    )

    # Получатели
    send_to_user = models.BooleanField(
        default=True, help_text="Отправлять пользователю"
    )
    send_to_owner = models.BooleanField(default=False, help_text="Отправлять владельцу")
    send_to_admins = models.BooleanField(default=False, help_text="Отправлять админам")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("event", "channel")

    def __str__(self):
        return f"{self.get_event_display()} - {self.get_channel_display()}"

    def render(self, context, language="ru"):
        """Рендеринг шаблона с контекстом"""
        templates = {
            "ru": self.template_ru,
            "kz": self.template_kz,
            "en": self.template_en,
        }

        template = templates.get(language) or self.template_ru

        # Подставляем переменные
        try:
            return template.format(**context)
        except KeyError as e:
            return template  # Возвращаем как есть если ошибка


class NotificationQueue(models.Model):
    """Очередь уведомлений"""

    STATUS_CHOICES = [
        ("pending", "В очереди"),
        ("processing", "Обрабатывается"),
        ("sent", "Отправлено"),
        ("failed", "Ошибка"),
        ("cancelled", "Отменено"),
    ]

    # Получатель
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    telegram_chat_id = models.CharField(max_length=255, blank=True)

    # Содержимое
    event = models.CharField(max_length=50)
    channel = models.CharField(max_length=20)
    message = models.TextField()
    context = models.JSONField(default=dict)

    # Статус
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    scheduled_for = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)

    # Дополнительно
    attempts = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
            models.Index(fields=["user", "created_at"]),
        ]
        ordering = ["scheduled_for"]

    def __str__(self):
        return f"{self.event} to {self.user or self.phone_number} via {self.channel}"


class NotificationLog(models.Model):
    """Лог отправленных уведомлений"""

    notification = models.ForeignKey(
        NotificationQueue, on_delete=models.CASCADE, related_name="logs"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20)
    message = models.TextField(blank=True)
    response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
