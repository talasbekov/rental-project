"""Domain services for booking workflows."""

from __future__ import annotations

from typing import Iterable, TYPE_CHECKING

from django.db import transaction  # type: ignore
from django.db.models import Q  # type: ignore
from django.db.utils import NotSupportedError  # type: ignore

from apps.properties.models import PropertyAvailability

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .models import Booking


class BookingConflictError(Exception):
    """Raised when a property is busy for requested dates."""


def _lock_queryset_if_possible(queryset):
    """Apply select_for_update when inside transaction.atomic()."""

    if not transaction.get_connection().in_atomic_block:
        return queryset

    try:
        return queryset.select_for_update()
    except NotSupportedError:
        return queryset


def ensure_property_is_available(
    property_obj,
    check_in,
    check_out,
    *,
    exclude_booking_id=None,
) -> None:
    """Ensure the property is free for the given period."""

    from .models import Booking  # Local import to prevent circular dependency

    overlapping_filter = Q(check_in__lt=check_out) & Q(check_out__gt=check_in)

    blocking_statuses: Iterable[str] = (
        Booking.Status.PENDING,
        Booking.Status.CONFIRMED,
        Booking.Status.IN_PROGRESS,
    )

    bookings_qs = Booking.objects.filter(
        property=property_obj,
        status__in=blocking_statuses,
    ).filter(overlapping_filter)

    if exclude_booking_id is not None:
        bookings_qs = bookings_qs.exclude(pk=exclude_booking_id)

    bookings_qs = _lock_queryset_if_possible(bookings_qs)

    if bookings_qs.exists():
        raise BookingConflictError("Объект недоступен на выбранные даты.")

    blocking_availability_statuses: Iterable[str] = (
        PropertyAvailability.AvailabilityStatus.BOOKED,
        PropertyAvailability.AvailabilityStatus.BLOCKED,
        PropertyAvailability.AvailabilityStatus.MAINTENANCE,
    )

    availability_qs = PropertyAvailability.objects.filter(
        property=property_obj,
        status__in=blocking_availability_statuses,
    ).filter(Q(start_date__lt=check_out) & Q(end_date__gt=check_in))

    availability_qs = _lock_queryset_if_possible(availability_qs)

    if availability_qs.exists():
        raise BookingConflictError("Объект недоступен на выбранные даты.")


@transaction.atomic
def reserve_dates_for_booking(booking: "Booking") -> None:
    """Creates a booked availability record for the booking period."""

    PropertyAvailability.objects.update_or_create(
        property=booking.property,
        start_date=booking.check_in,
        end_date=booking.check_out,
        defaults={
            "status": PropertyAvailability.AvailabilityStatus.BOOKED,
            "reason": f"Booking {booking.booking_code}",
            "source": "booking",
        },
    )


@transaction.atomic
def release_dates_for_booking(booking: "Booking") -> None:
    """Releases availability previously reserved for a booking."""

    PropertyAvailability.objects.filter(
        property=booking.property,
        start_date=booking.check_in,
        end_date=booking.check_out,
        source="booking",
    ).delete()
