"""Serializers for notifications."""

from __future__ import annotations

from rest_framework import serializers  # type: ignore

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications."""

    class Meta:
        model = Notification
        fields = ['id', 'user', 'title', 'message', 'is_read', 'created_at']
        read_only_fields = ['user', 'title', 'message', 'created_at']