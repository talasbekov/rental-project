"""Booking domain models for ZhilyeGO."""

from __future__ import annotations

import secrets
from decimal import Decimal

from django.conf import settings  # type: ignore
from django.core.exceptions import ValidationError  # type: ignore
from django.db import models, transaction  # type: ignore
from django.utils import timezone  # type: ignore
from django.utils.translation import gettext_lazy as _  # type: ignore


class Booking(models.Model):
    """Бронирование объекта недвижимости."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Ожидает подтверждения")
        CONFIRMED = "confirmed", _("Подтверждено")
        IN_PROGRESS = "in_progress", _("Гость заселён")
        COMPLETED = "completed", _("Завершено")
        CANCELLED_BY_GUEST = "cancelled_by_guest", _("Отменено гостем")
        CANCELLED_BY_REALTOR = "cancelled_by_realtor", _("Отменено риелтором")
        EXPIRED = "expired", _("Истёкло/не оплачено")

    class PaymentStatus(models.TextChoices):
        WAITING = "waiting", _("Ожидает оплаты")
        PAID = "paid", _("Оплачено")
        REFUNDED = "refunded", _("Возврат")
        FAILED = "failed", _("Ошибка оплаты")

    class CancellationSource(models.TextChoices):
        GUEST = "guest", _("Гость")
        REALTOR = "realtor", _("Риелтор")
        SYSTEM = "system", _("Система")

    guest = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    agency = models.ForeignKey(
        "users.RealEstateAgency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )
    booking_code = models.CharField(max_length=12, unique=True, editable=False)
    source = models.CharField(
        max_length=20,
        default="web",
        help_text=_("Источник бронирования (web, telegram, api)."),
    )
    check_in = models.DateField()
    check_out = models.DateField()
    guests_count = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.WAITING,
    )
    nightly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Фиксированная цена за ночь на момент брони."),
    )
    total_nights = models.PositiveSmallIntegerField(default=1)
    cleaning_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    service_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="KZT")
    special_requests = models.TextField(blank=True)
    payment_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Дата, до которой требуется оплата."),
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Таймаут удержания бронирования, после которого система отменяет бронь."),
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_source = models.CharField(
        max_length=20,
        choices=CancellationSource.choices,
        blank=True,
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Бронирование")
        verbose_name_plural = _("Бронирования")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(check_out__gt=models.F("check_in")),
                name="booking_valid_dates",
            ),
        ]
        indexes = [
            models.Index(fields=["property", "check_in", "check_out"]),
            models.Index(fields=["booking_code"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"Booking #{self.booking_code} for {self.property_id}"

    def clean(self) -> None:
        if self.check_in >= self.check_out:
            raise ValidationError(_("Дата выезда должна быть позже даты заезда."))

        self.total_nights = (self.check_out - self.check_in).days
        if self.total_nights <= 0:
            raise ValidationError(_("Продолжительность проживания должна быть не менее одной ночи."))

        # Фиксируем цену из объекта на момент бронирования (сезонные цены будут учтены сервисом)
        if not self.nightly_rate:
            self.nightly_rate = self.property.base_price

        self.cleaning_fee = self.property.cleaning_fee
        self.currency = self.property.currency
        subtotal = Decimal(self.total_nights) * self.nightly_rate
        subtotal += self.cleaning_fee + self.service_fee
        subtotal -= self.discount_amount
        self.total_price = max(subtotal, Decimal("0.00"))

        if self.guests_count > self.property.max_guests:
            raise ValidationError(
                _("Количество гостей превышает допустимое для выбранного объекта.")
            )

        if self.total_nights < self.property.min_nights or self.total_nights > self.property.max_nights:
            raise ValidationError(
                _("Период проживания должен соответствовать ограничениям объекта.")
            )

    def save(self, *args, **kwargs):  # type: ignore
        with transaction.atomic():
            creating = self._state.adding
            if creating and not self.booking_code:
                self.booking_code = self.generate_booking_code()
            self.clean()
            super().save(*args, **kwargs)

    @staticmethod
    def generate_booking_code() -> str:
        return secrets.token_hex(4).upper()

    def mark_cancelled(self, source: str, reason: str = "") -> None:
        self.status = (
            self.Status.CANCELLED_BY_GUEST if source == self.CancellationSource.GUEST else self.Status.CANCELLED_BY_REALTOR
        )
        self.cancellation_source = source
        self.cancellation_reason = reason
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "cancellation_source", "cancellation_reason", "cancelled_at"])
        from .services import release_dates_for_booking  # local import to avoid circular

        release_dates_for_booking(self)

    def mark_paid(self) -> None:
        self.payment_status = self.PaymentStatus.PAID
        self.status = self.Status.CONFIRMED
        self.save(update_fields=["payment_status", "status"])

    def should_expire(self) -> bool:
        return bool(self.expires_at and timezone.now() > self.expires_at and self.status == self.Status.PENDING)
