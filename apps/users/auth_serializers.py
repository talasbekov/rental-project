"""Serializers for authentication flows (register, login, password reset)."""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model  # type: ignore
from django.db import transaction  # type: ignore
from django.utils import timezone  # type: ignore
from rest_framework import serializers  # type: ignore

from apps.notifications.services import send_email_notification
from .models import PasswordResetToken


User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    phone = serializers.CharField()
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:  # type: ignore
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Пароли не совпадают."})
        email = attrs.get("email")
        phone = attrs.get("phone")
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": "Пользователь с таким email уже существует."})
        if phone and User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError({"phone": "Пользователь с таким телефоном уже существует."})
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]):  # type: ignore
        password = validated_data.pop("password")
        validated_data.pop("password_confirm", None)
        user = User.objects.create_user(password=password, **validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    login = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:  # type: ignore
        login = attrs.get("login", "")
        password = attrs.get("password", "")

        # Find user by email or phone
        try:
            if "@" in login:
                user = User.objects.get(email__iexact=login)
            else:
                user = User.objects.get(phone=login)
        except User.DoesNotExist:
            raise serializers.ValidationError({"login": "Неверный логин или пароль."})

        # Check lock
        if getattr(user, "is_locked", False):
            raise serializers.ValidationError({"non_field_errors": ["Аккаунт временно заблокирован. Попробуйте позже."]})

        if not user.check_password(password):
            # register failed attempt and potentially lock
            if hasattr(user, "register_failed_attempt"):
                user.register_failed_attempt(threshold=5)
            raise serializers.ValidationError({"login": "Неверный логин или пароль."})

        # Success: reset counters if any
        if hasattr(user, "unlock"):
            user.unlock()

        attrs["user"] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:  # type: ignore
        identifier = attrs.get("identifier", "")
        try:
            if "@" in identifier:
                user = User.objects.get(email__iexact=identifier)
            else:
                user = User.objects.get(phone=identifier)
        except User.DoesNotExist:
            raise serializers.ValidationError({"identifier": "Пользователь не найден."})
        attrs["user"] = user
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]):  # type: ignore
        user = validated_data["user"]
        # Invalidate previous tokens (optional soft invalidation)
        PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)

        # Generate 6-digit numeric code
        code = f"{random.randint(0, 999999):06d}"
        token = PasswordResetToken.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=15),
            attempts_left=3,
            is_used=False,
        )

        # Send email
        try:
            send_email_notification(
                recipient_email=user.email,
                subject="Код для восстановления пароля",
                template_name=None,
                context={"message": f"Ваш код для восстановления пароля: {code}"},
            )
        except Exception:
            pass

        return token


class PasswordResetConfirmSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    code = serializers.CharField()
    new_password = serializers.CharField(min_length=8)
    new_password_confirm = serializers.CharField(min_length=8)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:  # type: ignore
        if attrs.get("new_password") != attrs.get("new_password_confirm"):
            raise serializers.ValidationError({"new_password_confirm": "Пароли не совпадают."})
        identifier = attrs.get("identifier", "")
        try:
            if "@" in identifier:
                user = User.objects.get(email__iexact=identifier)
            else:
                user = User.objects.get(phone=identifier)
        except User.DoesNotExist:
            raise serializers.ValidationError({"identifier": "Пользователь не найден."})
        attrs["user"] = user
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]):  # type: ignore
        user = validated_data["user"]
        code = validated_data["code"]
        now = timezone.now()

        try:
            token = PasswordResetToken.objects.filter(
                user=user,
                is_used=False,
            ).latest("created_at")
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError({"code": "Код не найден. Запросите новый."})

        if token.is_expired:
            token.mark_used()
            raise serializers.ValidationError({"code": "Срок действия кода истёк."})

        if token.attempts_left == 0:
            token.mark_used()
            raise serializers.ValidationError({"code": "Превышено число попыток. Запросите новый код."})

        if token.code != code:
            token.decrement_attempt()
            raise serializers.ValidationError({"code": "Неверный код."})

        # Success: update password and mark token used
        user.set_password(validated_data["new_password"])
        user.save(update_fields=["password"])
        token.mark_used()
        return user

