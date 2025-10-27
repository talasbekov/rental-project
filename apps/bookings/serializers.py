"""Serializers for booking flows."""

from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from rest_framework import serializers

from apps.properties.models import Property
from apps.properties.serializers import PropertyDetailSerializer, PropertyListSerializer
from apps.users.serializers import UserSerializer

from .models import Booking, Review


class BookingSerializer(serializers.ModelSerializer):
    property = PropertyListSerializer(read_only=True)
    guest = UserSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = (
            "id",
            "property",
            "guest",
            "status",
            "check_in",
            "check_out",
            "guests_count",
            "total_amount",
            "special_request",
            "cancellation_reason",
            "cancelled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class BookingCreateSerializer(serializers.Serializer):
    property_id = serializers.UUIDField()
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    guests_count = serializers.IntegerField(min_value=1)
    special_request = serializers.CharField(required=False, allow_blank=True)

    def validate_property_id(self, value):
        try:
            prop = Property.objects.get(id=value, status=Property.Status.ACTIVE)
        except Property.DoesNotExist as exc:
            raise serializers.ValidationError("Объект не найден или недоступен.") from exc
        self.context["property"] = prop
        return value

    def validate(self, attrs):
        if attrs["check_in"] >= attrs["check_out"]:
            raise serializers.ValidationError("Дата выезда должна быть позже даты заезда.")
        return attrs

    def create(self, validated_data):
        guest = self.context["request"].user
        prop: Property = self.context["property"]
        try:
            booking = Booking.create_booking(
                guest=guest,
                property=prop,
                check_in=validated_data["check_in"],
                check_out=validated_data["check_out"],
                guests_count=validated_data["guests_count"],
                special_request=validated_data.get("special_request", ""),
            )
        except ValidationError as exc:
            raise serializers.ValidationError(exc.message) from exc
        return booking

    def to_representation(self, instance):
        return BookingSerializer(instance).data


class BookingDetailSerializer(BookingSerializer):
    property = PropertyDetailSerializer(read_only=True)


class ReviewSerializer(serializers.ModelSerializer):
    guest = UserSerializer(read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "booking",
            "property",
            "guest",
            "rating",
            "comment",
            "is_published",
            "created_at",
        )
        read_only_fields = fields


class ReviewCreateSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(min_length=10)

    def validate_booking_id(self, value):
        try:
            booking = Booking.objects.select_related("guest", "property").get(id=value)
        except Booking.DoesNotExist as exc:
            raise serializers.ValidationError("Бронирование не найдено") from exc
        if booking.guest_id != self.context["request"].user.id:
            raise serializers.ValidationError("Нельзя оставить отзыв на чужое бронирование")
        if booking.status != Booking.Status.COMPLETED:
            raise serializers.ValidationError("Отзыв доступен только после завершения пребывания")
        if hasattr(booking, "review"):
            raise serializers.ValidationError("Отзыв уже оставлен")
        self.context["booking"] = booking
        return value

    def create(self, validated_data):
        booking: Booking = self.context["booking"]
        review = Review.objects.create(
            booking=booking,
            property=booking.property,
            guest=booking.guest,
            rating=validated_data["rating"],
            comment=validated_data["comment"],
        )
        return review

    def to_representation(self, instance):
        return ReviewSerializer(instance).data
