"""Serializers for property catalog."""

from __future__ import annotations

from rest_framework import serializers

from .models import Amenity, Favorite, Property, PropertyPhoto


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ("id", "name", "category")


class PropertyPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyPhoto
        fields = ("id", "image", "is_primary", "order")


class PropertyListSerializer(serializers.ModelSerializer):
    primary_photo = serializers.SerializerMethodField()
    amenities = AmenitySerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = (
            "id",
            "title",
            "city",
            "district",
            "property_type",
            "property_class",
            "rooms",
            "sleeps",
            "base_price",
            "status",
            "amenities",
            "primary_photo",
        )

    def get_primary_photo(self, obj: Property):
        photo = obj.photos.filter(is_primary=True).first() or obj.photos.first()
        return PropertyPhotoSerializer(photo).data if photo else None


class PropertyDetailSerializer(serializers.ModelSerializer):
    amenities = AmenitySerializer(many=True, read_only=True)
    photos = PropertyPhotoSerializer(many=True, read_only=True)
    owner = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = (
            "id",
            "title",
            "description",
            "city",
            "district",
            "address_line",
            "latitude",
            "longitude",
            "property_type",
            "property_class",
            "rooms",
            "sleeps",
            "area",
            "floor",
            "total_floors",
            "base_price",
            "min_stay_nights",
            "max_stay_nights",
            "check_in_from",
            "check_in_to",
            "check_out_from",
            "check_out_to",
            "cancellation_policy",
            "amenities",
            "photos",
            "owner",
            "created_at",
            "updated_at",
        )

    def get_owner(self, obj: Property):
        user = obj.owner
        return {
            "id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
        }


class FavoriteSerializer(serializers.ModelSerializer):
    property = PropertyListSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = ("id", "property", "created_at")
        read_only_fields = fields


class FavoriteCreateSerializer(serializers.Serializer):
    property_id = serializers.UUIDField()

    def validate_property_id(self, value):
        if not Property.objects.filter(id=value, status=Property.Status.ACTIVE).exists():
            raise serializers.ValidationError("Объект недоступен или не существует.")
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        property_id = validated_data["property_id"]
        favorite, _ = Favorite.objects.get_or_create(user=user, property_id=property_id)
        return favorite

    def to_representation(self, instance):
        return FavoriteSerializer(instance).data
