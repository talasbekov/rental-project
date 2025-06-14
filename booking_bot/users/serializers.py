from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile
from django.db import transaction

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ('role', 'phone_number') # User field will be implicitly linked

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer() # Now it's a nested writable serializer

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'password', 'profile')
        extra_kwargs = {'password': {'write_only': True}}

    @transaction.atomic
    def create(self, validated_data):
        profile_data = validated_data.pop('profile')
        user = User.objects.create_user(**validated_data) # Use create_user to handle password hashing
        UserProfile.objects.create(user=user, **profile_data)
        return user

    # Optional: Add update method if you want to support updating profile via User endpoint
    # def update(self, instance, validated_data):
    #     profile_data = validated_data.pop('profile', None)
    #     # Update user fields
    #     instance = super().update(instance, validated_data)

    #     # Update profile fields if profile_data is provided
    #     if profile_data:
    #         profile_serializer = UserProfileSerializer(instance.profile, data=profile_data, partial=True)
    #         if profile_serializer.is_valid(raise_exception=True):
    #             profile_serializer.save()
    #     return instance


class TelegramUserSerializer(serializers.Serializer):
    telegram_chat_id = serializers.CharField(max_length=255)
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)

    def validate_telegram_chat_id(self, value):
        # Basic validation, can be expanded (e.g. check if numeric)
        if not value:
            raise serializers.ValidationError("Telegram chat ID cannot be empty.")
        return value
