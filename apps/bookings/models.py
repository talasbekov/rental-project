"""Booking domain models for ЖильеGO."""

from __future__ import annotations

import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class BookingQuerySet(models.QuerySet):
    def overlapping(self, property_id: uuid.UUID, check_in: date, check_out: date):
        return self.filter(
            property_id=property_id,
            status__in=[
                Booking.Status.PENDING,
                Booking.Status.CONFIRMED,
                Booking.Status.IN_PROGRESS,
            ],
            check_in__lt=check_out,
            check_out__gt=check_in,
        )


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает подтверждения"
        CONFIRMED = "confirmed", "Подтверждено"
        IN_PROGRESS = "in_progress", "В процессе проживания"
        COMPLETED = "completed", "Завершено"
        CANCELLED_BY_GUEST = "cancelled_by_guest", "Отменено гостем"
        CANCELLED_BY_REALTOR = "cancelled_by_realtor", "Отменено риелтором"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guest = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    property = models.ForeignKey("properties.Property", on_delete=models.CASCADE, related_name="bookings")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)

    check_in = models.DateField()
    check_out = models.DateField()
    guests_count = models.PositiveSmallIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    special_request = models.TextField(blank=True)

    cancellation_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BookingQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("guest", "status")),
            models.Index(fields=("property", "status")),
        ]

    def clean(self):
        if self.check_in >= self.check_out:
            raise ValidationError("Дата выезда должна быть позже даты заезда.")
        if self.guests_count <= 0:
            raise ValidationError("Количество гостей должно быть положительным.")

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    def cancel(self, *, by_guest: bool, reason: str | None = None) -> None:
        if self.status not in {self.Status.PENDING, self.Status.CONFIRMED, self.Status.IN_PROGRESS}:
            raise ValidationError("Эту бронь нельзя отменить.")
        self.status = self.Status.CANCELLED_BY_GUEST if by_guest else self.Status.CANCELLED_BY_REALTOR
        self.cancellation_reason = reason or ""
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "cancellation_reason", "cancelled_at", "updated_at"])

    @classmethod
    def create_booking(
        cls,
        *,
        guest,
        property,
        check_in: date,
        check_out: date,
        guests_count: int,
        special_request: str = "",
    ) -> "Booking":
        if guests_count > property.sleeps:
            raise ValidationError("Превышено допустимое количество гостей")

        nights = (check_out - check_in).days
        if nights <= 0:
            raise ValidationError("Минимальная длительность брони — 1 ночь")
        if nights < property.min_stay_nights:
            raise ValidationError("Длительность проживания меньше минимально допустимой")
        if property.max_stay_nights and nights > property.max_stay_nights:
            raise ValidationError("Длительность проживания превышает максимально допустимую")

        with transaction.atomic():
            if cls.objects.overlapping(property.id, check_in, check_out).select_for_update().exists():
                raise ValidationError("Объект недоступен на выбранные даты")
            total_amount = property.base_price * nights
            booking = cls.objects.create(
                guest=guest,
                property=property,
                check_in=check_in,
                check_out=check_out,
                guests_count=guests_count,
                total_amount=total_amount,
                special_request=special_request,
            )
        return booking


class Review(models.Model):
    """Guest review left after completed booking."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="review")
    property = models.ForeignKey("properties.Property", on_delete=models.CASCADE, related_name="reviews")
    guest = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("property", "is_published"))]

    def clean(self):
        if self.booking.guest_id != self.guest_id:
            raise ValidationError("Гость не соответствует бронированию.")
        if self.booking.property_id != self.property_id:
            raise ValidationError("Объект не соответствует бронированию.")
        if self.booking.status != Booking.Status.COMPLETED:
            raise ValidationError("Отзыв можно оставить только после завершения бронирования.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
