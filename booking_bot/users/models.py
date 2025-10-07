# booking_bot/users/models.py

from django.db import models
from django.conf import settings


class RealEstateAgency(models.Model):
    """Группа объектов и администраторов под единым брендом."""

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users_realestateagency"
        verbose_name = "Real Estate Agency"
        verbose_name_plural = "Real Estate Agencies"

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Профиль пользователя с дополнительными полями"""

    ROLE_USER = "user"
    ROLE_ADMIN = "admin"
    ROLE_SUPER_ADMIN = "super_admin"
    ROLE_SUPER_USER = "super_user"

    ADMIN_ROLES = (ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_SUPER_USER)
    SUPERVISOR_ROLES = (ROLE_SUPER_ADMIN, ROLE_SUPER_USER)

    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_SUPER_ADMIN, "Super Admin"),
        (ROLE_SUPER_USER, "Super User"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        null=False,
        blank=False
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_USER
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

    agency = models.ForeignKey(
        RealEstateAgency,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
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
            models.Index(fields=['agency']),
        ]

    def __str__(self):
        if self.user:
            if hasattr(self.user, "get_username"):
                return f"{self.user.get_username()} - {self.role}"
            return f"{getattr(self.user, 'username', 'unknown')} - {self.role}"
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

        if not self.user:
            raise ValueError("UserProfile.user must be set before saving")

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

    # --- Role helpers -------------------------------------------------

    def has_admin_access(self) -> bool:
        return self.role in self.ADMIN_ROLES

    def has_super_admin_access(self) -> bool:
        return self.role in self.SUPERVISOR_ROLES

    def has_super_user_access(self) -> bool:
        return self.role == self.ROLE_SUPER_USER
