# Добавьте или исправьте в файле booking_bot/users/models.py

from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """Профиль пользователя с дополнительными полями"""

    ROLE_CHOICES = [
        ('user', 'User'),
        ('admin', 'Admin'),
        ('super_admin', 'Super Admin'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='user'
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    telegram_chat_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        db_index=True
    )

    telegram_state = models.JSONField(
        default=dict,
        blank=True
    )

    whatsapp_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    whatsapp_state = models.JSONField(
        default=dict,
        blank=True
    )

    ko_factor = models.FloatField(
        default=0.0,
        help_text="Коэффициент отмен пользователя (0-1)"
    )

    # ВАЖНО: Поле должно иметь default=False
    requires_prepayment = models.BooleanField(
        default=False,  # Значение по умолчанию
        help_text="Требуется ли предоплата от этого пользователя"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_userprofile'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    def save(self, *args, **kwargs):
        # Убедимся, что обязательные поля заполнены
        if self.requires_prepayment is None:
            self.requires_prepayment = False
        if self.ko_factor is None:
            self.ko_factor = 0.0
        if self.telegram_state is None:
            self.telegram_state = {}
        if self.whatsapp_state is None:
            self.whatsapp_state = {}

        super().save(*args, **kwargs)