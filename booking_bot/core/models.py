from django.db import models

from booking_bot.bookings.views import User


# Create your models here.
class AuditLog(models.Model):
    """Журнал аудита доступа к конфиденциальным данным"""

    ACTION_CHOICES = [
        ('view_code', 'Просмотр кода доступа'),
        ('send_code', 'Отправка кода доступа'),
        ('update_code', 'Изменение кода доступа'),
        ('view_phone', 'Просмотр телефона'),
        ('export_data', 'Экспорт данных'),
        ('view_payment', 'Просмотр платежных данных'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=50)  # 'property', 'booking', etc.
    object_id = models.IntegerField()
    details = models.JSONField(default=dict)  # Дополнительная информация
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Для Telegram/WhatsApp ботов
    telegram_chat_id = models.CharField(max_length=255, null=True, blank=True)
    whatsapp_phone = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['object_type', 'object_id']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"

    @classmethod
    def log(cls, user, action, obj, request=None, details=None, **kwargs):
        """Удобный метод для логирования"""
        log_entry = cls(
            user=user,
            action=action,
            object_type=obj.__class__.__name__.lower(),
            object_id=obj.id,
            details=details or {}
        )

        if request:
            log_entry.ip_address = cls.get_client_ip(request)
            log_entry.user_agent = request.META.get('HTTP_USER_AGENT', '')

        # Добавляем дополнительные поля
        for key, value in kwargs.items():
            if hasattr(log_entry, key):
                setattr(log_entry, key, value)

        log_entry.save()
        return log_entry

    @staticmethod
    def get_client_ip(request):
        """Получение IP адреса клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip