"""Service layer for Telegram bot workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model  # type: ignore
from django.core.exceptions import ObjectDoesNotExist  # type: ignore
from django.db import transaction  # type: ignore
from django.utils import timezone  # type: ignore

from apps.notifications.services import send_email_notification
from apps.users.models import CustomUser
from .models import TelegramProfile, TelegramVerificationCode

UserModel = get_user_model()


@dataclass
class RegistrationResult:
    user: CustomUser
    profile: TelegramProfile
    created: bool


def get_or_create_profile(telegram_id: int, chat_id: int, **kwargs) -> TelegramProfile:
    defaults = {
        "chat_id": chat_id,
    }
    defaults.update({k: v for k, v in kwargs.items() if v is not None})
    profile, _ = TelegramProfile.objects.get_or_create(telegram_id=telegram_id, defaults=defaults)
    # Обновляем служебные поля при каждом вызове
    for field, value in defaults.items():
        setattr(profile, field, value)
    profile.save(update_fields=list(defaults.keys()))
    return profile


@transaction.atomic
def register_new_user(
    profile: TelegramProfile,
    email: str,
    phone: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> RegistrationResult:
    """Создает нового пользователя и привязывает профиль Telegram."""

    if UserModel.objects.filter(email__iexact=email).exists():
        raise ValueError("Пользователь с таким email уже существует.")
    if UserModel.objects.filter(phone=phone).exists():
        raise ValueError("Пользователь с таким телефоном уже существует.")

    from django.contrib.auth.hashers import make_password
    import secrets

    # Generate random password
    random_password = secrets.token_urlsafe(16)

    user: CustomUser = UserModel.objects.create_user(
        email=email,
        password=random_password,
        phone=phone,
        first_name=first_name or "",
        last_name=last_name or "",
        role=CustomUser.RoleChoices.GUEST,
    )
    profile.user = user
    profile.phone = phone
    profile.is_registered = True
    profile.save(update_fields=["user", "phone", "is_registered"])

    send_email_notification(
        recipient_email=email,
        subject="Добро пожаловать в ЖильеGO",
        template_name=None,
        context={
            "message": (
                "Здравствуйте! Мы создали для вас аккаунт ЖильеGO через Telegram. "
                "Пожалуйста, завершите настройку и задайте постоянный пароль в веб-интерфейсе."
            )
        },
    )

    return RegistrationResult(user=user, profile=profile, created=True)


def initiate_link_existing_account(profile: TelegramProfile, identifier: str) -> TelegramVerificationCode:
    """Ищет пользователя по email/телефону и отправляет код подтверждения."""

    try:
        if "@" in identifier:
            user = UserModel.objects.get(email__iexact=identifier)
        else:
            user = UserModel.objects.get(phone=identifier)
    except ObjectDoesNotExist as exc:
        raise ValueError("Пользователь не найден.") from exc

    verification = TelegramVerificationCode.generate(user=user, profile=profile)
    send_email_notification(
        recipient_email=user.email,
        subject="Код подтверждения Telegram",
        template_name=None,
        context={
            "message": f"Ваш код подтверждения для привязки Telegram: {verification.code}",
        },
    )
    return verification


def confirm_link_code(profile: TelegramProfile, code: str) -> bool:
    """Проверяет введенный код и привязывает Telegram к существующему аккаунту."""

    verification = (
        profile.verification_codes.filter(is_confirmed=False)
        .order_by("-created_at")
        .first()
    )
    if not verification:
        raise ValueError("Активный код подтверждения не найден.")
    if verification.verify(code):
        profile.user = verification.user
        profile.phone = profile.phone or verification.user.phone or ""
        profile.save(update_fields=["user", "phone"])
        return True
    return False


def format_user_name(user: CustomUser) -> str:
    if user.first_name:
        return f"{user.first_name} {user.last_name}".strip()
    return user.email
