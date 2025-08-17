# booking_bot/users/models.py

from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """Профиль пользователя с дополнительными полями"""

    ROLE_CHOICES = [
        ('user', 'User'),
        ('admin', 'Admin'),
        ('super_admin', 'Super Admin'),
    ]

    # ИСПРАВЛЕНИЕ: делаем user необязательным при создании, но добавляем проверки
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        null=True,  # Временно разрешаем NULL
        blank=True
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

    requires_prepayment = models.BooleanField(
        default=False,
        help_text="Требуется ли предоплата от этого пользователя"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_userprofile'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
        # Добавляем индекс для быстрого поиска
        indexes = [
            models.Index(fields=['telegram_chat_id']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        if self.user:
            return f"{self.user.username} - {self.role}"
        else:
            return f"Profile {self.id} - {self.role} (no user)"

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

    def ensure_user_exists(self):
        """Убедиться, что у профиля есть связанный пользователь"""
        if not self.user and self.telegram_chat_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            username = f"telegram_{self.telegram_chat_id}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": "",
                    "last_name": "",
                }
            )
            if created:
                user.set_unusable_password()
                user.save()

            self.user = user
            self.save()

        return self.user
