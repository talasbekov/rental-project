"""Models supporting Telegram bot workflows."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings  # type: ignore
from django.db import models  # type: ignore
from django.utils import timezone  # type: ignore
from django.utils.translation import gettext_lazy as _  # type: ignore


class TelegramProfile(models.Model):
    """Telegram user linked to платформенный аккаунт."""

    telegram_id = models.BigIntegerField(unique=True)
    chat_id = models.BigIntegerField(help_text="Чат, используемый для диалога.")
    username = models.CharField(max_length=64, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    language_code = models.CharField(max_length=10, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="telegram_profiles",
    )
    is_registered = models.BooleanField(
        default=False,
        help_text=_("Создан ли аккаунт через бота."),
    )
    last_command = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Telegram профиль")
        verbose_name_plural = _("Telegram профили")

    def __str__(self) -> str:
        return f"{self.telegram_id} ({self.username or 'unknown'})"


class TelegramVerificationCode(models.Model):
    """6-значные коды для привязки Telegram к существующим аккаунтам."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_verification_codes",
    )
    profile = models.ForeignKey(
        TelegramProfile,
        on_delete=models.CASCADE,
        related_name="verification_codes",
    )
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    attempts_left = models.PositiveSmallIntegerField(default=3)
    is_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Telegram код подтверждения")
        verbose_name_plural = _("Telegram коды подтверждения")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Code {self.code} for user {self.user_id}"

    @classmethod
    def generate(cls, user, profile, ttl_minutes: int = 10) -> "TelegramVerificationCode":  # type: ignore
        cls.objects.filter(user=user, profile=profile, is_confirmed=False).delete()
        code = secrets.token_hex(3).upper()[:6]
        return cls.objects.create(
            user=user,
            profile=profile,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
            attempts_left=3,
        )

    def verify(self, value: str) -> bool:
        if self.is_confirmed:
            return True
        if self.attempts_left == 0:
            return False
        if timezone.now() > self.expires_at:
            return False
        if value.strip().upper() != self.code.upper():
            self.attempts_left = max(self.attempts_left - 1, 0)
            self.save(update_fields=["attempts_left"])
            return False
        self.is_confirmed = True
        self.save(update_fields=["is_confirmed"])
        return True
