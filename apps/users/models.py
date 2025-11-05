"""User domain models for ZhilyeGO.

The platform differentiates four основных роли (гость, риелтор,
супер-администратор агентства, суперпользователь) и требует хранения
дополнительных атрибутов безопасности, подтверждений и связей с
агентствами. Модели ниже реализуют эти требования в соответствии
с техническим заданием и пользовательскими сценариями.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractUser, BaseUserManager  # type: ignore
from django.core.validators import RegexValidator  # type: ignore
from django.db import models  # type: ignore
from django.utils import timezone  # type: ignore
from django.utils.translation import gettext_lazy as _  # type: ignore


PHONE_VALIDATOR = RegexValidator(
    regex=r"^\+?\d{7,15}$",
    message=_("Неверный формат телефона. Используйте международный формат без пробелов."),
)


class CustomUserManager(BaseUserManager):
    """Менеджер пользователей, использующий email в качестве логина."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields: Any):
        if not email:
            raise ValueError("Email обязателен для создания пользователя.")
        email = self.normalize_email(email)

        phone = extra_fields.get("phone")
        if phone:
            extra_fields["phone"] = self.normalize_phone(phone)

        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", CustomUser.RoleChoices.GUEST)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields: Any):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", CustomUser.RoleChoices.SUPERUSER)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Суперпользователь должен иметь is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Суперпользователь должен иметь is_superuser=True.")

        return self._create_user(email, password, **extra_fields)

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Удаляем пробелы и дефисы для унификации хранения телефона."""
        return phone.replace(" ", "").replace("-", "")


class RealEstateAgency(models.Model):
    """Агентство недвижимости под управлением Super Admin."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, unique=True, validators=[PHONE_VALIDATOR])
    email = models.EmailField(unique=True)
    website = models.URLField(blank=True)
    telegram_chat_id = models.BigIntegerField(null=True, blank=True)
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.0,
        help_text=_("Комиссия агентства в процентах."),
    )
    properties_limit = models.PositiveIntegerField(
        default=0, help_text=_("0 означает отсутствие ограничений по количеству объектов.")
    )
    realtors_limit = models.PositiveIntegerField(
        default=0, help_text=_("0 означает отсутствие ограничений по количеству риелторов.")
    )
    owner = models.OneToOneField(
        "CustomUser",
        on_delete=models.SET_NULL,
        related_name="managed_agency",
        null=True,
        blank=True,
        help_text=_("Супер Админ агентства."),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Агентство недвижимости")
        verbose_name_plural = _("Агентства недвижимости")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"


class CustomUser(AbstractUser):
    """Пользователь платформы с расширенными атрибутами и ролями."""

    class RoleChoices(models.TextChoices):
        GUEST = "guest", _("Гость")
        REALTOR = "realtor", _("Риелтор")
        SUPER_ADMIN = "super_admin", _("Супер Админ")
        SUPERUSER = "superuser", _("Суперпользователь")

    username = models.CharField(
        _("Отображаемое имя"),
        max_length=150,
        blank=True,
        help_text=_("Опционально, используется в интерфейсах и уведомлениях."),
    )
    email = models.EmailField(_("Email"), unique=True)
    phone = models.CharField(
        _("Телефон"),
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        validators=[PHONE_VALIDATOR],
    )
    role = models.CharField(
        _("Роль"),
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.GUEST,
    )
    agency = models.ForeignKey(
        RealEstateAgency,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employees",
    )
    avatar = models.ImageField(_("Аватар"), upload_to="avatars/", blank=True, null=True)
    telegram_id = models.BigIntegerField(_("Telegram ID"), unique=True, null=True, blank=True)
    is_email_verified = models.BooleanField(_("Email подтверждён"), default=False)
    is_phone_verified = models.BooleanField(_("Телефон подтверждён"), default=False)
    is_identity_verified = models.BooleanField(_("KYC пройден"), default=False)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(_("Блокировка до"), null=True, blank=True)
    last_activity_at = models.DateTimeField(_("Последняя активность"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = _("Пользователь")
        verbose_name_plural = _("Пользователи")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.email} ({self.get_role_display()})"

    # --- Доменные помощники -------------------------------------------------
    def mark_email_verified(self) -> None:
        self.is_email_verified = True
        self.save(update_fields=["is_email_verified"])

    def mark_phone_verified(self) -> None:
        self.is_phone_verified = True
        self.save(update_fields=["is_phone_verified"])

    def is_realtor(self) -> bool:
        return self.role == self.RoleChoices.REALTOR

    def is_super_admin(self) -> bool:
        return self.role == self.RoleChoices.SUPER_ADMIN

    def is_platform_superuser(self) -> bool:
        return self.role == self.RoleChoices.SUPERUSER or self.is_superuser

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    def lock(self, minutes: int = 15) -> None:
        self.locked_until = timezone.now() + timezone.timedelta(minutes=minutes)
        self.failed_login_attempts = 0
        self.save(update_fields=["locked_until", "failed_login_attempts"])

    def unlock(self) -> None:
        self.locked_until = None
        self.failed_login_attempts = 0
        self.save(update_fields=["locked_until", "failed_login_attempts"])

    def register_failed_attempt(self, threshold: int = 5) -> None:
        self.failed_login_attempts += 1
        update_fields = ["failed_login_attempts"]
        if self.failed_login_attempts >= threshold:
            self.lock()
            return
        self.save(update_fields=update_fields)

    def touch_last_activity(self) -> None:
        self.last_activity_at = timezone.now()
        self.save(update_fields=["last_activity_at"])


class PasswordResetToken(models.Model):
    """Токен восстановления пароля с ограничением по времени и попыткам."""

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    attempts_left = models.PositiveSmallIntegerField(default=3)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Токен восстановления пароля")
        verbose_name_plural = _("Токены восстановления пароля")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"Reset token for {self.user_id}: {self.code}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def mark_used(self) -> None:
        self.is_used = True
        self.save(update_fields=["is_used"])

    def decrement_attempt(self) -> None:
        if self.attempts_left > 0:
            self.attempts_left -= 1
            self.save(update_fields=["attempts_left"])


# Backwards compatibility alias used in legacy modules/tests
User = CustomUser
