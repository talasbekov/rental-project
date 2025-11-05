"""Serializers for the favorites domain."""

from __future__ import annotations

from rest_framework import serializers  # type: ignore

from .models import Favorite


class FavoriteCreateSerializer(serializers.ModelSerializer):
    """Serializer for adding a property to favorites."""

    class Meta:
        model = Favorite
        fields = ['property']


class PropertyShortSerializer(serializers.Serializer):
    """Краткая информация о объекте для списка избранных."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()
    city = serializers.CharField()
    district = serializers.CharField()
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    property_class = serializers.CharField()
    rooms = serializers.IntegerField()
    max_guests = serializers.IntegerField()
    status = serializers.CharField()

    # Дополнительная информация
    average_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    main_photo_url = serializers.SerializerMethodField()

    def get_average_rating(self, obj):  # type: ignore
        """Средний рейтинг объекта."""
        from django.db.models import Avg  # type: ignore
        avg = obj.reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
        return round(avg, 1) if avg else None

    def get_reviews_count(self, obj):  # type: ignore
        """Количество отзывов."""
        return obj.reviews.count()

    def get_main_photo_url(self, obj):  # type: ignore
        """URL главной фотографии."""
        primary_photo = obj.photos.filter(is_primary=True).first()
        photo = primary_photo or obj.photos.first()
        image_field = getattr(photo, "image", None) if photo else None
        if not image_field:
            return None
        try:
            return image_field.url
        except ValueError:
            # File exists in DB but missing on storage
            return None


class FavoriteSerializer(serializers.ModelSerializer):
    """Serializer for listing favorites."""

    user_id = serializers.ReadOnlyField(source='user.id')
    property_id = serializers.ReadOnlyField(source='property.id')
    property = PropertyShortSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = ['id', 'user_id', 'property_id', 'property', 'created_at']


class FavoriteToggleSerializer(serializers.Serializer):
    """Serializer for toggling favorite status."""

    property_id = serializers.IntegerField(required=True)

    def validate_property_id(self, value: int) -> int:  # type: ignore
        """Проверяем, что объект существует."""
        from apps.properties.models import Property

        if not Property.objects.filter(id=value, status='active').exists():
            raise serializers.ValidationError("Объект не найден или неактивен.")
        return value


class FavoriteBulkDeleteSerializer(serializers.Serializer):
    """Serializer for bulk deleting favorites."""

    favorite_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        help_text="Список ID избранных для удаления"
    )
