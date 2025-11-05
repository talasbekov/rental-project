"""Serializers for the booking domain."""

from __future__ import annotations

from datetime import date

from django.db import transaction  # type: ignore
from django.utils import timezone  # type: ignore

from rest_framework import serializers  # type: ignore

from .models import Booking
from .services import BookingConflictError, ensure_property_is_available


class BookingCreateSerializer(serializers.ModelSerializer):
    """Создание брони гостем."""

    check_in = serializers.DateField()
    check_out = serializers.DateField()
    guests_count = serializers.IntegerField(min_value=1, default=1)

    class Meta:
        model = Booking
        fields = [
            "property",
            "check_in",
            "check_out",
            "guests_count",
            "special_requests",
        ]
        extra_kwargs = {
            "special_requests": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):  # type: ignore
        check_in: date = attrs["check_in"]
        check_out: date = attrs["check_out"]
        if check_in >= check_out:
            raise serializers.ValidationError("Дата выезда должна быть позже даты заезда.")
        property_obj = attrs["property"]
        if property_obj.status != property_obj.Status.ACTIVE:
            raise serializers.ValidationError("Объект недоступен для бронирования.")
        return attrs

    def create(self, validated_data):  # type: ignore
        request = self.context["request"]
        guest = request.user
        validated = dict(validated_data)
        property_obj = validated.pop("property")
        expires_at = timezone.now() + timezone.timedelta(minutes=15)
        payment_deadline = timezone.now() + timezone.timedelta(hours=24)

        with transaction.atomic():
            try:
                ensure_property_is_available(
                    property_obj,
                    validated_data["check_in"],
                    validated_data["check_out"],
                )
            except BookingConflictError as exc:
                raise serializers.ValidationError({"non_field_errors": [str(exc)]})

            booking = Booking.objects.create(
                guest=guest,
                agency=property_obj.agency,
                expires_at=expires_at,
                payment_deadline=payment_deadline,
                property=property_obj,
                **validated,
            )
        return booking


class BookingSerializer(serializers.ModelSerializer):
    """Детальный сериализатор бронирования."""

    guest_id = serializers.ReadOnlyField(source="guest.id")
    property_id = serializers.ReadOnlyField(source="property.id")
    agency_id = serializers.ReadOnlyField(source="agency.id")
    property_title = serializers.ReadOnlyField(source="property.title")

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_code",
            "guest_id",
            "property_id",
            "agency_id",
            "property_title",
            "source",
            "check_in",
            "check_out",
            "guests_count",
            "status",
            "payment_status",
            "nightly_rate",
            "total_nights",
            "cleaning_fee",
            "service_fee",
            "discount_amount",
            "total_price",
            "currency",
            "special_requests",
            "payment_deadline",
            "expires_at",
            "cancelled_at",
            "cancellation_source",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "booking_code",
            "guest_id",
            "property_id",
            "agency_id",
            "property_title",
            "status",
            "payment_status",
            "nightly_rate",
            "total_nights",
            "cleaning_fee",
            "service_fee",
            "discount_amount",
            "total_price",
            "currency",
            "payment_deadline",
            "expires_at",
            "cancelled_at",
            "cancellation_source",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]
