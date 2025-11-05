"""Serializers for the properties domain."""

from __future__ import annotations

from datetime import date

from django.utils import timezone  # type: ignore
from rest_framework import serializers  # type: ignore

from .models import (
    Amenity,
    Property,
    PropertyAccessInfo,
    PropertyAccessLog,
    PropertyAvailability,
    PropertyCalendarSettings,
    PropertyPhoto,
    PropertySeasonalRate,
    PropertyType,
)


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ["id", "name", "category", "icon"]


class PropertyTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyType
        fields = ["id", "slug", "name", "description"]


class PropertyPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyPhoto
        fields = ["id", "image", "caption", "order", "is_primary", "uploaded_at"]
        read_only_fields = ["uploaded_at"]


class PropertySeasonalRateSerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source="created_by_id")
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = PropertySeasonalRate
        fields = [
            "id",
            "start_date",
            "end_date",
            "price_per_night",
            "min_nights",
            "max_nights",
            "description",
            "color_code",
            "priority",
            "created_by",
            "created_at",
            "updated_at",
            "status_label",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at", "status_label"]

    def get_status_label(self, obj: PropertySeasonalRate) -> str:
        return f"{obj.start_date:%d.%m.%Y} - {obj.end_date:%d.%m.%Y}"


class PropertySeasonalRateWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertySeasonalRate
        fields = [
            "start_date",
            "end_date",
            "price_per_night",
            "min_nights",
            "max_nights",
            "description",
            "color_code",
            "priority",
        ]

    def validate(self, attrs):  # type: ignore
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and start > end:
            raise serializers.ValidationError("Дата окончания не может быть ранее даты начала.")
        return attrs


class PropertyAvailabilitySerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source="created_by_id")
    status_display = serializers.ReadOnlyField(source="get_status_display")
    availability_type_display = serializers.ReadOnlyField(source="get_availability_type_display")

    class Meta:
        model = PropertyAvailability
        fields = [
            "id",
            "start_date",
            "end_date",
            "status",
            "status_display",
            "availability_type",
            "availability_type_display",
            "reason",
            "source",
            "repeat_rule",
            "color_code",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_by",
            "created_at",
            "updated_at",
            "status_display",
            "availability_type_display",
        ]


class PropertyAvailabilityWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyAvailability
        fields = [
            "start_date",
            "end_date",
            "status",
            "availability_type",
            "reason",
            "repeat_rule",
            "color_code",
        ]

    def validate(self, attrs):  # type: ignore
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and start > end:
            raise serializers.ValidationError("Дата окончания не может быть ранее даты начала.")
        repeat_rule = attrs.get("repeat_rule") or PropertyAvailability.RepeatRule.NONE
        if repeat_rule != PropertyAvailability.RepeatRule.NONE:
            raise serializers.ValidationError(
                "Поддержка повторяющихся блокировок пока недоступна."
            )
        return attrs


class PropertyCalendarSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyCalendarSettings
        fields = [
            "default_price",
            "advance_notice",
            "booking_window",
            "allowed_check_in_days",
            "allowed_check_out_days",
            "auto_apply_seasonal",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_booking_window(self, value: int) -> int:  # type: ignore
        if value <= 0:
            raise serializers.ValidationError("Горизонт бронирования должен быть больше нуля.")
        if value > 1095:
            raise serializers.ValidationError("Горизонт бронирования не может превышать 3 года.")
        return value

    def validate_allowed_check_in_days(self, value):  # type: ignore
        return self._validate_week_days(value, "allowed_check_in_days")

    def validate_allowed_check_out_days(self, value):  # type: ignore
        return self._validate_week_days(value, "allowed_check_out_days")

    @staticmethod
    def _validate_week_days(value, field_name):  # type: ignore
        if not isinstance(value, list):
            raise serializers.ValidationError("Значение должно быть списком.")
        for item in value:
            if item not in range(0, 7):
                raise serializers.ValidationError(
                    f"{field_name}: допускаются значения от 0 (понедельник) до 6 (воскресенье)."
                )
        return value


class PropertyPublicCalendarSerializer(serializers.Serializer):
    """Используется для возврата агрегированных данных календаря гостю."""

    date = serializers.DateField()
    status = serializers.CharField()
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    pricing_source = serializers.CharField()
    min_nights = serializers.IntegerField()



class PropertySerializer(serializers.ModelSerializer):
    """Read serializer with nested relations."""

    owner_id = serializers.ReadOnlyField(source="owner.id")
    agency_id = serializers.ReadOnlyField(source="agency.id")
    property_type = PropertyTypeSerializer(read_only=True)
    amenities = AmenitySerializer(many=True, read_only=True)
    photos = PropertyPhotoSerializer(many=True, read_only=True)
    seasonal_rates = PropertySeasonalRateSerializer(many=True, read_only=True)
    availability_periods = PropertyAvailabilitySerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = [
            "id",
            "owner_id",
            "agency_id",
            "title",
            "slug",
            "description",
            "status",
            "property_type",
            "property_class",
            "city",
            "district",
            "address_line",
            "entrance",
            "floor",
            "floor_total",
            "latitude",
            "longitude",
            "area_sqm",
            "rooms",
            "bedrooms",
            "bathrooms",
            "max_guests",
            "sleeping_places",
            "has_children_allowed",
            "has_pets_allowed",
            "has_smoking_allowed",
            "has_events_allowed",
            "base_price",
            "cleaning_fee",
            "security_deposit",
            "currency",
            "min_nights",
            "max_nights",
            "check_in_from",
            "check_in_to",
            "check_out_from",
            "check_out_to",
            "cancellation_policy",
            "additional_rules",
            "amenities",
            "photos",
            "seasonal_rates",
            "availability_periods",
            "is_featured",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "owner_id",
            "agency_id",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        ]


class PropertyWriteSerializer(serializers.ModelSerializer):
    """Serializer for create/update operations."""

    amenities = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Amenity.objects.all(),
        required=False,
    )
    property_type = serializers.PrimaryKeyRelatedField(
        queryset=PropertyType.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Property
        fields = [
            "title",
            "slug",
            "description",
            "property_type",
            "property_class",
            "city",
            "district",
            "address_line",
            "entrance",
            "floor",
            "floor_total",
            "latitude",
            "longitude",
            "area_sqm",
            "rooms",
            "bedrooms",
            "bathrooms",
            "max_guests",
            "sleeping_places",
            "has_children_allowed",
            "has_pets_allowed",
            "has_smoking_allowed",
            "has_events_allowed",
            "base_price",
            "cleaning_fee",
            "security_deposit",
            "currency",
            "min_nights",
            "max_nights",
            "check_in_from",
            "check_in_to",
            "check_out_from",
            "check_out_to",
            "cancellation_policy",
            "additional_rules",
            "amenities",
            "is_featured",
        ]
        extra_kwargs = {
            "slug": {"required": False, "allow_blank": True},
        }

    def create(self, validated_data):  # type: ignore
        amenities = validated_data.pop("amenities", [])
        property_instance = Property.objects.create(
            owner=self.context["request"].user,
            agency=getattr(self.context["request"].user, "agency", None),
            **validated_data,
        )
        if amenities:
            property_instance.amenities.set(amenities)
        return property_instance

    def update(self, instance: Property, validated_data):  # type: ignore
        amenities = validated_data.pop("amenities", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if amenities is not None:
            instance.amenities.set(amenities)
        return instance


class PropertyAccessInfoSerializer(serializers.ModelSerializer):
    """
    Serializer for PropertyAccessInfo.

    WARNING: This serializer exposes sensitive encrypted data.
    Only use with proper authorization checks!
    """

    class Meta:
        model = PropertyAccessInfo
        fields = [
            "id",
            "property",
            "door_code",
            "apartment_code",
            "safe_code",
            "instructions",
            "contact_phone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class PropertyAccessLogSerializer(serializers.ModelSerializer):
    """Serializer for access logs (audit trail)."""

    accessed_by_email = serializers.ReadOnlyField(source="accessed_by.email")
    property_title = serializers.ReadOnlyField(source="access_info.property.title")

    class Meta:
        model = PropertyAccessLog
        fields = [
            "id",
            "access_info",
            "property_title",
            "accessed_by",
            "accessed_by_email",
            "field_name",
            "reason",
            "ip_address",
            "accessed_at",
        ]
        read_only_fields = ["accessed_at"]
