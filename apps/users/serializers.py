"""Serializers for user-related API endpoints."""

from __future__ import annotations

from django.contrib.auth import get_user_model  # type: ignore
from rest_framework import serializers  # type: ignore

from .models import PHONE_VALIDATOR, RealEstateAgency

User = get_user_model()


class AgencyShortSerializer(serializers.ModelSerializer):
    """Краткая информация об агентстве в ответах API."""

    class Meta:
        model = RealEstateAgency
        fields = ["id", "name", "city", "phone", "email"]


class UserSerializer(serializers.ModelSerializer):
    """Основной сериализатор пользователя."""

    agency = AgencyShortSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone",
            "role",
            "agency",
            "avatar",
            "telegram_id",
            "is_email_verified",
            "is_phone_verified",
            "is_identity_verified",
            "last_activity_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "role",
            "agency",
            "is_email_verified",
            "is_phone_verified",
            "is_identity_verified",
            "last_activity_at",
            "created_at",
            "updated_at",
        ]


class RegisterSerializer(serializers.ModelSerializer):
    """Регистрация гостя по email и телефону."""

    password = serializers.CharField(write_only=True, min_length=8)
    phone = serializers.CharField(validators=[PHONE_VALIDATOR])

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "phone",
            "first_name",
            "last_name",
            "username",
        ]
        extra_kwargs = {
            "first_name": {"required": False, "allow_blank": True},
            "last_name": {"required": False, "allow_blank": True},
            "username": {"required": False, "allow_blank": True},
        }

    def create(self, validated_data):  # type: ignore
        password = validated_data.pop("password")
        # guests регистрируются как role=guest, подтверждения выставляются процессов
        user = User.objects.create_user(password=password, **validated_data)
        return user
