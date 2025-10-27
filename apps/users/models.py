"""User domain models for ЖильеGO."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class RealEstateAgency(models.Model):
    """Minimal representation of a real estate agency."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return self.name


class UserManager(BaseUserManager):
    """Custom manager with email as username field."""

    use_in_migrations = True

    def _create_user(self, email: str, phone: str, password: str | None, **extra_fields) -> "User":
        if not email:
            raise ValueError("Email is required")
        if not phone:
            raise ValueError("Phone number is required")

        email = self.normalize_email(email)
        phone = User.normalize_phone(phone)

        user = self.model(email=email, phone=phone, **extra_fields)
        user.full_clean(exclude={"last_login"})
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, phone: str, password: str | None = None, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, phone, password, **extra_fields)

    def create_superuser(
        self, email: str, phone: str, password: str | None = None, **extra_fields
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.SUPERUSER)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Core user model with role support and security helpers."""

    class Role(models.TextChoices):
        GUEST = "guest", "Гость"
        REALTOR = "realtor", "Риелтор"
        SUPER_ADMIN = "super_admin", "Супер Админ"
        SUPERUSER = "superuser", "Суперпользователь"

    PHONE_VALIDATOR = RegexValidator(
        regex=r"^\+?[0-9]{9,15}$",
        message="Введите корректный номер телефона в международном формате.",
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email address", unique=True)
    phone = models.CharField("phone number", max_length=20, unique=True, validators=[PHONE_VALIDATOR])
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.GUEST)
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    agency = models.ForeignKey(
        RealEstateAgency,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    is_email_verified = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone"]

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return self.email

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Keep only leading + and digits."""
        clean_digits = "".join(ch for ch in phone if ch.isdigit())
        has_plus = phone.strip().startswith("+")
        return f"+{clean_digits}" if has_plus else clean_digits

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failed_attempt(self, *, lock_after: int = 5, lock_minutes: int = 15) -> None:
        """Increment failed attempts counter and lock account if threshold reached."""
        self.failed_login_attempts += 1
        update_fields = ["failed_login_attempts", "updated_at"]

        if self.failed_login_attempts >= lock_after:
            self.locked_until = timezone.now() + timedelta(minutes=lock_minutes)
            self.failed_login_attempts = 0
            update_fields.append("locked_until")

        self.save(update_fields=update_fields)

    def reset_failed_attempts(self) -> None:
        if self.failed_login_attempts or self.locked_until:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.save(update_fields=["failed_login_attempts", "locked_until", "updated_at"])


class PasswordResetToken(models.Model):
    """Stores short-lived password reset confirmation codes."""

    CODE_LENGTH = 6

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_tokens")
    code = models.CharField(max_length=CODE_LENGTH)
    expires_at = models.DateTimeField()
    attempts_left = models.PositiveSmallIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("code",)),
            models.Index(fields=("expires_at",)),
        ]

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def decrease_attempts(self) -> None:
        if self.attempts_left > 0:
            self.attempts_left -= 1
            self.save(update_fields=["attempts_left"])
