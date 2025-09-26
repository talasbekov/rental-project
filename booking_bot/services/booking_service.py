"""Сервисные функции для работы с бронированиями."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from booking_bot.bookings.models import Booking
from booking_bot.listings.models import Property, PropertyCalendarManager

logger = logging.getLogger(__name__)

User = get_user_model()


class BookingError(Exception):
    """Базовое исключение для ошибок операции бронирования."""


@dataclass
class BookingRequest:
    user: User
    property: Property
    start_date: date
    end_date: date
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    status: str = "pending_payment"
    hold_calendar: bool = False
    expires_in: Optional[timedelta] = timedelta(minutes=15)


def calculate_total_price(property_obj: Property, start: date, end: date) -> float:
    """Расчёт стоимости исходя из количества ночей."""
    duration = (end - start).days
    if duration <= 0:
        raise BookingError("Минимальный срок бронирования - 1 день")
    return float(duration * property_obj.price_per_day)


def _ensure_availability(property_obj: Property, start: date, end: date) -> None:
    """Проверка доступности объекта на указанные даты."""
    if not PropertyCalendarManager.check_availability(property_obj, start, end):
        raise BookingError("Выбранные даты уже забронированы или недоступны")

    conflict_exists = Booking.objects.filter(
        property=property_obj,
        status__in=["pending_payment", "confirmed"],
        start_date__lt=end,
        end_date__gt=start,
    ).exists()
    if conflict_exists:
        raise BookingError("Выбранные даты уже забронированы")


@transaction.atomic
def create_booking(request: BookingRequest) -> Booking:
    """Создание бронирования с учётом блокировок и проверок."""
    locked_property = Property.objects.select_for_update().get(id=request.property.id)

    _ensure_availability(locked_property, request.start_date, request.end_date)

    total_price = calculate_total_price(locked_property, request.start_date, request.end_date)

    expires_at = (
        timezone.now() + request.expires_in if request.expires_in else None
    )

    booking = Booking.objects.create(
        user=request.user,
        property=locked_property,
        start_date=request.start_date,
        end_date=request.end_date,
        check_in_time=request.check_in_time,
        check_out_time=request.check_out_time,
        total_price=total_price,
        status=request.status,
        expires_at=expires_at,
    )

    if request.hold_calendar:
        PropertyCalendarManager.block_dates(
            locked_property,
            request.start_date,
            request.end_date,
            booking=booking,
            status="booked",
        )

    logger.info("Booking %s created via service", booking.id)
    return booking


@transaction.atomic
def cancel_booking(booking: Booking, reason: Optional[str] = None) -> Booking:
    """Отмена бронирования с освобождением календаря."""
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if booking.status == "cancelled":
        return booking

    booking.status = "cancelled"
    booking.cancelled_at = timezone.now()
    if reason:
        booking.cancel_reason = reason
    booking.save()

    PropertyCalendarManager.release_dates(
        booking.property, booking.start_date, booking.end_date
    )

    logger.info("Booking %s cancelled via service", booking.id)
    return booking
