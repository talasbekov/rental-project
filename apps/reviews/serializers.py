"""Serializers for reviews.

Provide both read and write serializers for the ``Review`` model.
Validates that rating values fall within the expected range. The
creating user is inferred from the request in the view.
"""

from __future__ import annotations

from rest_framework import serializers  # type: ignore

from .models import Review, ReviewPhoto


class ReviewPhotoSerializer(serializers.ModelSerializer):
    """Serializer for review photos."""

    class Meta:
        model = ReviewPhoto
        fields = ['id', 'image', 'caption', 'order', 'uploaded_at']
        read_only_fields = ['uploaded_at']


class ReviewCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new review."""

    class Meta:
        model = Review
        fields = [
            'property',
            'booking',
            'rating',
            'comment',
            'cleanliness_rating',
            'location_rating',
            'value_rating',
            'communication_rating',
            'accuracy_rating',
            'check_in_rating',
        ]

    def validate_rating(self, value: int) -> int:  # type: ignore
        if value < 1 or value > 5:
            raise serializers.ValidationError('Рейтинг должен быть между 1 и 5.')
        return value

    def _validate_optional_rating(self, value: int | None) -> int | None:  # type: ignore
        """Общая валидация для опциональных рейтингов."""
        if value is not None and (value < 1 or value > 5):
            raise serializers.ValidationError('Оценка должна быть между 1 и 5.')
        return value

    def validate_cleanliness_rating(self, value: int | None) -> int | None:  # type: ignore
        return self._validate_optional_rating(value)

    def validate_location_rating(self, value: int | None) -> int | None:  # type: ignore
        return self._validate_optional_rating(value)

    def validate_value_rating(self, value: int | None) -> int | None:  # type: ignore
        return self._validate_optional_rating(value)

    def validate_communication_rating(self, value: int | None) -> int | None:  # type: ignore
        return self._validate_optional_rating(value)

    def validate_accuracy_rating(self, value: int | None) -> int | None:  # type: ignore
        return self._validate_optional_rating(value)

    def validate_check_in_rating(self, value: int | None) -> int | None:  # type: ignore
        return self._validate_optional_rating(value)


class ReviewSerializer(serializers.ModelSerializer):
    """Read serializer for reviews including related ids."""

    user_id = serializers.ReadOnlyField(source='user.id')
    user_name = serializers.ReadOnlyField(source='user.username')
    property_id = serializers.ReadOnlyField(source='property.id')
    property_title = serializers.ReadOnlyField(source='property.title')
    booking_code = serializers.ReadOnlyField(source='booking.booking_code')
    average_rating = serializers.ReadOnlyField()
    photos = ReviewPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Review
        fields = [
            'id',
            'user_id',
            'user_name',
            'property_id',
            'property_title',
            'booking_code',
            'rating',
            'comment',
            'cleanliness_rating',
            'location_rating',
            'value_rating',
            'communication_rating',
            'accuracy_rating',
            'check_in_rating',
            'average_rating',
            'photos',
            'realtor_response',
            'realtor_response_at',
            'is_approved',
            'created_at',
            'updated_at',
        ]


class RealtorResponseSerializer(serializers.Serializer):
    """Serializer for realtor response to a review."""

    realtor_response = serializers.CharField(
        max_length=2000,
        required=True,
        help_text="Ответ владельца на отзыв"
    )