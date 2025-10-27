"""
Booking Domain Entities

Core business entities for the booking domain:
- Booking: Main aggregate representing a reservation
- BookingStatus: FSM states for booking lifecycle
- PaymentStatus: Payment state tracking
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from shared.domain.base import Aggregate
from shared.domain.value_objects import Money, DateRange


class BookingStatus(Enum):
    """
    Booking Status Finite State Machine

    State transitions:
    - HOLD -> CONFIRMED (payment succeeded)
    - HOLD -> EXPIRED (15 min timeout, no payment)
    - HOLD -> CANCELLED (user cancelled before payment)
    - CONFIRMED -> CHECKED_IN (guest checked in)
    - CONFIRMED -> CANCELLED (user or realtor cancelled)
    - CHECKED_IN -> COMPLETED (guest checked out)
    """
    HOLD = 'hold'                          # Waiting for payment (15 min)
    CONFIRMED = 'confirmed'                # Paid and confirmed
    CHECKED_IN = 'checked_in'              # Guest has checked in
    COMPLETED = 'completed'                # Guest has checked out
    CANCELLED = 'cancelled'                # Cancelled by user or realtor
    EXPIRED = 'expired'                    # Hold timeout expired


class PaymentStatus(Enum):
    """Payment status tracking"""
    PENDING = 'pending'     # Waiting for payment
    PAID = 'paid'           # Payment successful
    FAILED = 'failed'       # Payment failed
    REFUNDED = 'refunded'   # Payment refunded (after cancellation)


@dataclass
class Booking(Aggregate):
    """
    Booking Aggregate Root

    Represents a guest's reservation of a property for specific dates.
    This is the main aggregate that enforces booking business rules.

    Key invariants:
    - Booking must have valid date range (check_in < check_out)
    - Hold status expires after 15 minutes
    - Only confirmed/checked_in bookings block property dates
    - Guests count must not exceed property capacity
    """

    # Booking identification
    booking_number: str  # Human-readable booking number (e.g., BK20251027123456)

    # References
    property_id: UUID
    guest_id: UUID

    # Dates
    dates: DateRange
    guests_count: int

    # Pricing
    price_per_night: Money
    total_price: Money
    discount: Money = field(default_factory=lambda: Money(0, 'KZT'))
    final_price: Money = field(default_factory=lambda: Money(0, 'KZT'))

    # Guest contact information
    guest_name: str = ''
    guest_phone: str = ''
    guest_email: str = ''
    special_requests: str = ''

    # Status tracking
    status: BookingStatus = BookingStatus.HOLD
    payment_status: PaymentStatus = PaymentStatus.PENDING
    hold_expires_at: datetime | None = None

    # Cancellation details
    cancellation_reason: str = ''
    refund_amount: Money | None = None

    # Timestamps
    confirmed_at: datetime | None = None
    checked_in_at: datetime | None = None
    checked_out_at: datetime | None = None
    cancelled_at: datetime | None = None

    def __post_init__(self):
        """Initialize booking with HOLD status and expiry time"""
        super().__post_init__()

        # Validate guests count
        if self.guests_count < 1:
            raise ValueError("Guests count must be at least 1")

        # Set hold expiry for new bookings
        if self.status == BookingStatus.HOLD and not self.hold_expires_at:
            self.hold_expires_at = datetime.now() + timedelta(minutes=15)

        # Calculate final price if not set
        if self.final_price.amount == 0:
            self.final_price = self.total_price - self.discount

    def confirm_payment(self, payment_id: UUID):
        """
        Confirm payment (HOLD -> CONFIRMED)

        This transition happens when payment succeeds.
        Events: BookingConfirmed
        """
        if self.status != BookingStatus.HOLD:
            raise ValueError(
                f"Cannot confirm payment from status {self.status.value}. "
                f"Booking must be in HOLD status."
            )

        if self.is_expired():
            raise ValueError(
                f"Cannot confirm expired booking. "
                f"Hold expired at {self.hold_expires_at}"
            )

        # Import here to avoid circular dependency
        from apps.bookings.domain.events import BookingConfirmed

        # Transition state
        self.status = BookingStatus.CONFIRMED
        self.payment_status = PaymentStatus.PAID
        self.confirmed_at = datetime.now()
        self.hold_expires_at = None  # Clear hold expiry

        # Emit domain event
        self.add_event(BookingConfirmed(
            aggregate_id=self.id,
            booking_id=self.id,
            property_id=self.property_id,
            guest_id=self.guest_id,
            payment_id=payment_id,
            dates=self.dates
        ))

    def check_in(self):
        """
        Check in guest (CONFIRMED -> CHECKED_IN)

        Called when guest arrives at the property.
        Events: BookingCheckedIn
        """
        if self.status != BookingStatus.CONFIRMED:
            raise ValueError(
                f"Cannot check in from status {self.status.value}. "
                f"Booking must be CONFIRMED."
            )

        from apps.bookings.domain.events import BookingCheckedIn

        self.status = BookingStatus.CHECKED_IN
        self.checked_in_at = datetime.now()

        self.add_event(BookingCheckedIn(
            aggregate_id=self.id,
            booking_id=self.id,
            property_id=self.property_id
        ))

    def complete(self):
        """
        Complete booking (CHECKED_IN -> COMPLETED)

        Called when guest checks out.
        Events: BookingCompleted
        """
        if self.status != BookingStatus.CHECKED_IN:
            raise ValueError(
                f"Cannot complete booking from status {self.status.value}. "
                f"Booking must be CHECKED_IN."
            )

        from apps.bookings.domain.events import BookingCompleted

        self.status = BookingStatus.COMPLETED
        self.checked_out_at = datetime.now()

        self.add_event(BookingCompleted(
            aggregate_id=self.id,
            booking_id=self.id,
            property_id=self.property_id,
            guest_id=self.guest_id
        ))

    def cancel(self, reason: str, refund_amount: Money | None = None):
        """
        Cancel booking

        Can be called from HOLD, CONFIRMED, or CHECKED_IN states.
        Cannot cancel COMPLETED or EXPIRED bookings.
        Events: BookingCancelled
        """
        if self.status in [BookingStatus.COMPLETED, BookingStatus.EXPIRED]:
            raise ValueError(
                f"Cannot cancel booking with status {self.status.value}"
            )

        from apps.bookings.domain.events import BookingCancelled

        old_status = self.status
        self.status = BookingStatus.CANCELLED
        self.cancellation_reason = reason
        self.refund_amount = refund_amount
        self.cancelled_at = datetime.now()

        # Update payment status
        if refund_amount and refund_amount.amount > 0:
            self.payment_status = PaymentStatus.REFUNDED

        self.add_event(BookingCancelled(
            aggregate_id=self.id,
            booking_id=self.id,
            property_id=self.property_id,
            reason=reason,
            refund_amount=refund_amount,
            old_status=old_status.value
        ))

    def expire(self):
        """
        Expire booking (HOLD -> EXPIRED)

        Called by Celery task when hold timeout is reached.
        Events: BookingExpired
        """
        if self.status != BookingStatus.HOLD:
            raise ValueError(
                f"Cannot expire booking with status {self.status.value}. "
                f"Only HOLD bookings can expire."
            )

        from apps.bookings.domain.events import BookingExpired

        self.status = BookingStatus.EXPIRED

        self.add_event(BookingExpired(
            aggregate_id=self.id,
            booking_id=self.id,
            property_id=self.property_id
        ))

    def is_expired(self) -> bool:
        """Check if hold has expired"""
        if self.status != BookingStatus.HOLD:
            return False
        if not self.hold_expires_at:
            return False
        return datetime.now() > self.hold_expires_at

    def can_be_cancelled(self) -> bool:
        """Check if booking can be cancelled"""
        return self.status not in [BookingStatus.COMPLETED, BookingStatus.EXPIRED, BookingStatus.CANCELLED]

    def blocks_dates(self) -> bool:
        """
        Check if this booking blocks property dates

        Only HOLD, CONFIRMED, and CHECKED_IN bookings block dates.
        """
        return self.status in [
            BookingStatus.HOLD,
            BookingStatus.CONFIRMED,
            BookingStatus.CHECKED_IN
        ]

    @property
    def nights(self) -> int:
        """Number of nights"""
        return len(self.dates)

    @property
    def is_active(self) -> bool:
        """Check if booking is active (not cancelled/expired/completed)"""
        return self.status in [
            BookingStatus.HOLD,
            BookingStatus.CONFIRMED,
            BookingStatus.CHECKED_IN
        ]

    def __str__(self):
        return f"Booking {self.booking_number} ({self.status.value})"

    def __repr__(self):
        return (
            f"Booking(id={self.id}, booking_number={self.booking_number}, "
            f"status={self.status.value}, dates={self.dates})"
        )