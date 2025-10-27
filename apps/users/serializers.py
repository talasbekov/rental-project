"""Serializers for authentication and user onboarding flows."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import serializers

from .models import PasswordResetToken, User


def _generate_reset_code(length: int = PasswordResetToken.CODE_LENGTH) -> str:
    return get_random_string(length=length, allowed_chars="0123456789")


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "role",
            "telegram_id",
            "is_email_verified",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = (
            "email",
            "phone",
            "first_name",
            "last_name",
            "password",
            "password_confirm",
        )

    def validate_phone(self, value: str) -> str:
        return User.normalize_phone(value)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Пароли не совпадают."})
        return attrs

    def create(self, validated_data: dict[str, Any]) -> User:
        password = validated_data.pop("password")
        validated_data.pop("password_confirm")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    login = serializers.CharField(help_text="Email или телефон")
    password = serializers.CharField(write_only=True)
    remember_me = serializers.BooleanField(default=False, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        login_value = attrs["login"].strip()
        password = attrs["password"]

        user = User.objects.filter(email__iexact=login_value).first() or User.objects.filter(
            phone=User.normalize_phone(login_value)
        ).first()

        if not user:
            raise serializers.ValidationError({"login": "Неверные учетные данные."})

        if not user.is_active:
            raise serializers.ValidationError({"login": "Аккаунт деактивирован."})

        if user.is_locked:
            raise serializers.ValidationError({"login": "Аккаунт заблокирован. Попробуйте позже."})

        if not user.check_password(password):
            user.register_failed_attempt()
            raise serializers.ValidationError({"login": "Неверные учетные данные."})

        user.reset_failed_attempts()
        attrs["user"] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Email или телефон")

    def validate_identifier(self, value: str) -> str:
        value = value.strip()
        if "@" in value:
            user = User.objects.filter(email__iexact=value).first()
        else:
            user = User.objects.filter(phone=User.normalize_phone(value)).first()

        if not user:
            raise serializers.ValidationError("Пользователь не найден.")

        self.context["user"] = user
        return value

    def save(self, **kwargs: Any) -> PasswordResetToken:
        user: User = self.context["user"]
        code = _generate_reset_code()
        expires_at = timezone.now() + timedelta(minutes=15)

        PasswordResetToken.objects.filter(user=user).delete()
        token = PasswordResetToken.objects.create(user=user, code=code, expires_at=expires_at)
        return token


class PasswordResetConfirmSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Email или телефон")
    code = serializers.CharField(max_length=PasswordResetToken.CODE_LENGTH)
    new_password = serializers.CharField(min_length=8)
    new_password_confirm = serializers.CharField(min_length=8)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        identifier = attrs["identifier"].strip()
        if "@" in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
        else:
            user = User.objects.filter(phone=User.normalize_phone(identifier)).first()

        if not user:
            raise serializers.ValidationError({"identifier": "Пользователь не найден."})

        token = PasswordResetToken.objects.filter(user=user, code=attrs["code"]).first()
        if not token:
            raise serializers.ValidationError({"code": "Неверный код подтверждения."})

        if token.is_expired():
            token.delete()
            raise serializers.ValidationError({"code": "Код истек. Запросите новый."})

        if token.attempts_left == 0:
            token.delete()
            raise serializers.ValidationError({"code": "Превышено число попыток. Запросите новый код."})

        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Пароли не совпадают."})

        attrs["user"] = user
        attrs["token"] = token
        return attrs

    def save(self, **kwargs: Any) -> User:
        user: User = self.validated_data["user"]
        token: PasswordResetToken = self.validated_data["token"]
        user.set_password(self.validated_data["new_password"])
        user.reset_failed_attempts()
        user.save(update_fields=["password", "updated_at", "failed_login_attempts", "locked_until"])
        token.delete()
        return user
