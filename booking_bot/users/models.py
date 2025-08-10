from django.contrib.auth.models import User
from django.db import models

class UserProfile(models.Model):
    USER_ROLE_CHOICES = [
        ('user', 'User'),
        ('admin', 'Admin'),
        ('super_admin', 'Super Admin'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=USER_ROLE_CHOICES, default='user')

    phone_number = models.CharField(max_length=20, blank=True, null=True)
    telegram_chat_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    telegram_state = models.JSONField(default=dict, blank=True)

    whatsapp_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text="Номер WhatsApp пользователя (без +)",
    )
    whatsapp_state = models.JSONField(default=dict, blank=True)

    # KO‑фактор: доля отмен бронирований для гостя
    ko_factor = models.FloatField(
        default=0.0,
        help_text="Доля отмен бронирований (KO‑фактор)",
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user.username} - {self.get_role_display()}"
