"""
Booking Domain Events

Events that represent things that have happened in the booking domain.
These are published after successful transaction commits.
"""

from dataclasses import dataclass
from uuid import UUID

from shared.domain.base import DomainEvent
from shared.domain.value_objects import Money, DateRange


# ===== Booking Events =====

@dataclass
class BookingCreated(DomainEvent):
    """
    Event: A new booking was created

    Triggers:
    - Send confirmation email to guest
    - Notify property owner
    - Start hold expiry timer (Celery task)
    """
    booking_id: UUID
    property_id: UUID
    guest_id: UUID
    dates: DateRange
    total_price: Money


@dataclass
class BookingConfirmed(DomainEvent):
    """
    Event: Booking payment confirmed (HOLD -> CONFIRMED)

    Triggers:
    - Send booking confirmation to guest
    - Send property access codes to guest
    - Notify property owner of confirmed booking
    - Update analytics
    """
    booking_id: UUID
    property_id: UUID
    guest_id: UUID
    payment_id: UUID
    dates: DateRange


@dataclass
class BookingCheckedIn(DomainEvent):
    """
    Event: Guest has checked in (CONFIRMED -> CHECKED_IN)

    Triggers:
    - Send check-out reminder
    - Update property status
    """
    booking_id: UUID
    property_id: UUID


@dataclass
class BookingCompleted(DomainEvent):
    """
    Event: Guest has checked out (CHECKED_IN -> COMPLETED)

    Triggers:
    - Request review from guest
    - Calculate and schedule payout to property owner
    - Update property availability
    - Update analytics
    """
    booking_id: UUID
    property_id: UUID
    guest_id: UUID


@dataclass
class BookingCancelled(DomainEvent):
    """
    Event: Booking was cancelled

    Triggers:
    - Process refund (if applicable)
    - Notify guest and property owner
    - Free up property dates
    - Update analytics
    """
    booking_id: UUID
    property_id: UUID
    reason: str
    refund_amount: Money | None
    old_status: str  # Status before cancellation


@dataclass
class BookingExpired(DomainEvent):
    """
    Event: Booking hold expired without payment (HOLD -> EXPIRED)

    Triggers:
    - Free up property dates
    - Notify guest (optional)
    - Update analytics
    """
    booking_id: UUID
    property_id: UUID


# ===== Inventory Events =====

@dataclass
class InventoryAllocated(DomainEvent):
    """
    Event: Dates allocated in inventory

    This means dates are now blocked for the property.
    """
    property_id: UUID
    allocation_id: UUID
    booking_id: UUID
    dates: DateRange


@dataclass
class InventoryDeallocated(DomainEvent):
    """
    Event: Dates deallocated in inventory

    This means dates are now available again.
    """
    property_id: UUID
    allocation_id: UUID
    booking_id: UUID