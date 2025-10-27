"""
Booking Command Handlers

These are the use cases for the booking domain.
They orchestrate domain operations within transactions.

Commands:
- CreateBookingCommand: Create a new booking
- ConfirmBookingCommand: Confirm payment for a booking
- CancelBookingCommand: Cancel a booking
- CheckInBookingCommand: Check in a guest
- CompleteBookingCommand: Complete a booking (check out)
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
import logging

from shared.application.uow import DjangoUnitOfWork
from shared.domain.value_objects import Money, DateRange
from apps.bookings.domain.entities import Booking, BookingStatus
from apps.bookings.domain.inventory import Inventory
from apps.bookings.domain.events import BookingCreated

logger = logging.getLogger(__name__)


# ===== Commands =====

@dataclass
class CreateBookingCommand:
    """
    Command to create a new booking

    This is the primary entry point for creating bookings.
    """
    property_id: UUID
    guest_id: UUID
    check_in: date
    check_out: date
    guests_count: int
    guest_name: str
    guest_phone: str
    guest_email: str
    special_requests: str = ''


@dataclass
class ConfirmBookingCommand:
    """Command to confirm a booking after successful payment"""
    booking_id: UUID
    payment_id: UUID


@dataclass
class CancelBookingCommand:
    """Command to cancel a booking"""
    booking_id: UUID
    reason: str
    cancelled_by: UUID  # User who cancelled (guest or realtor)


@dataclass
class CheckInBookingCommand:
    """Command to check in a guest"""
    booking_id: UUID


@dataclass
class CompleteBookingCommand:
    """Command to complete a booking (check out)"""
    booking_id: UUID


# ===== Command Handlers =====

class CreateBookingHandler:
    """
    Handler for CreateBooking command

    This implements the critical business logic for creating bookings
    with double booking prevention.

    Strategy (Defense in Depth):
    1. Start database transaction (atomic)
    2. Load Inventory aggregate with SELECT FOR UPDATE (pessimistic lock)
    3. Check availability in domain (can_allocate)
    4. Create Booking aggregate
    5. Allocate dates in Inventory aggregate
    6. Collect events from both aggregates
    7. Save both aggregates (within transaction)
    8. Commit transaction
    9. Publish events (after commit)
    10. PostgreSQL EXCLUDE constraint as final safety net
    """

    def __init__(self, booking_repo, inventory_repo):
        self.booking_repo = booking_repo
        self.inventory_repo = inventory_repo

    def handle(self, command: CreateBookingCommand) -> Booking:
        """
        Handle booking creation

        Returns: Created Booking aggregate

        Raises:
            ValueError: If property not found, dates not available, or validation fails
        """
        logger.info(
            f"Creating booking for property {command.property_id}, "
            f"guest {command.guest_id}, dates {command.check_in} - {command.check_out}"
        )

        # Get property to calculate pricing
        from apps.properties.models import Property as PropertyModel

        try:
            property_model = PropertyModel.objects.get(
                id=command.property_id,
                status='active'
            )
        except PropertyModel.DoesNotExist:
            raise ValueError(f"Property {command.property_id} not found or not active")

        # Validate dates
        if command.check_in >= command.check_out:
            raise ValueError("Check-out date must be after check-in date")

        if command.check_in < date.today():
            raise ValueError("Check-in date cannot be in the past")

        # Validate guests count
        if command.guests_count > property_model.sleeping_places:
            raise ValueError(
                f"Guests count ({command.guests_count}) exceeds property capacity "
                f"({property_model.sleeping_places})"
            )

        # Create date range
        dates = DateRange(command.check_in, command.check_out)

        # Calculate pricing
        nights = len(dates)
        price_per_night = Money(property_model.price_per_night, 'KZT')
        total_price = price_per_night * nights
        discount = Money(Decimal('0'), 'KZT')  # TODO: Apply discount logic
        final_price = total_price - discount

        # Start Unit of Work (transaction)
        with DjangoUnitOfWork() as uow:
            # Load Inventory with pessimistic lock (SELECT FOR UPDATE)
            # This prevents race conditions
            inventory = self.inventory_repo.get_by_property_id(
                command.property_id,
                lock=True
            )

            # If no inventory exists, create it
            if not inventory:
                inventory = Inventory(
                    id=uuid4(),
                    property_id=command.property_id
                )
                logger.info(f"Created new inventory for property {command.property_id}")

            # Check availability (domain validation)
            if not inventory.can_allocate(dates):
                # Get overlapping allocations for better error message
                overlapping = inventory.get_allocations_for_period(dates)
                raise ValueError(
                    f"Property not available for dates {dates}. "
                    f"Found {len(overlapping)} overlapping allocation(s)."
                )

            # Generate booking number
            booking_number = self._generate_booking_number()

            # Create Booking aggregate
            booking = Booking(
                id=uuid4(),
                booking_number=booking_number,
                property_id=command.property_id,
                guest_id=command.guest_id,
                dates=dates,
                guests_count=command.guests_count,
                price_per_night=price_per_night,
                total_price=total_price,
                discount=discount,
                final_price=final_price,
                guest_name=command.guest_name,
                guest_phone=command.guest_phone,
                guest_email=command.guest_email,
                special_requests=command.special_requests,
                status=BookingStatus.HOLD,
                hold_expires_at=datetime.now() + timedelta(minutes=15)
            )

            # Add BookingCreated event
            booking.add_event(BookingCreated(
                aggregate_id=booking.id,
                booking_id=booking.id,
                property_id=command.property_id,
                guest_id=command.guest_id,
                dates=dates,
                total_price=total_price
            ))

            # Allocate dates in inventory
            inventory.allocate(booking.id, dates)

            # Collect events from both aggregates
            uow.collect_events(booking)
            uow.collect_events(inventory)

            # Save to database (within transaction)
            self.booking_repo.save(booking)
            self.inventory_repo.save(inventory)

            # Transaction commits here automatically (__exit__)
            # Events are published after commit

        logger.info(
            f"Booking created successfully: {booking.booking_number} "
            f"(ID: {booking.id})"
        )

        return booking

    def _generate_booking_number(self) -> str:
        """Generate unique booking number: BK{timestamp}{random}"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_part = uuid4().hex[:6].upper()
        return f"BK{timestamp}{random_part}"


class ConfirmBookingHandler:
    """Handler for confirming booking after payment"""

    def __init__(self, booking_repo):
        self.booking_repo = booking_repo

    def handle(self, command: ConfirmBookingCommand):
        """Confirm booking"""
        logger.info(f"Confirming booking {command.booking_id} with payment {command.payment_id}")

        with DjangoUnitOfWork() as uow:
            # Load booking
            booking = self.booking_repo.get_by_id(command.booking_id)
            if not booking:
                raise ValueError(f"Booking {command.booking_id} not found")

            # Confirm payment (FSM transition HOLD -> CONFIRMED)
            booking.confirm_payment(command.payment_id)

            # Collect events
            uow.collect_events(booking)

            # Save changes
            self.booking_repo.save(booking)
            # Event: BookingConfirmed

        logger.info(f"Booking {booking.booking_number} confirmed successfully")


class CancelBookingHandler:
    """Handler for cancelling booking"""

    def __init__(self, booking_repo, inventory_repo):
        self.booking_repo = booking_repo
        self.inventory_repo = inventory_repo

    def handle(self, command: CancelBookingCommand):
        """Cancel booking and deallocate inventory"""
        logger.info(f"Cancelling booking {command.booking_id}, reason: {command.reason}")

        with DjangoUnitOfWork() as uow:
            # Load booking
            booking = self.booking_repo.get_by_id(command.booking_id)
            if not booking:
                raise ValueError(f"Booking {command.booking_id} not found")

            # Check if can be cancelled
            if not booking.can_be_cancelled():
                raise ValueError(
                    f"Booking {booking.booking_number} cannot be cancelled. "
                    f"Current status: {booking.status.value}"
                )

            # Calculate refund based on cancellation policy
            refund_amount = self._calculate_refund(booking)

            # Cancel booking (FSM transition)
            booking.cancel(command.reason, refund_amount)

            # Deallocate inventory (free up dates)
            inventory = self.inventory_repo.get_by_property_id(
                booking.property_id,
                lock=True
            )

            if inventory:
                inventory.deallocate(booking.id)
                uow.collect_events(inventory)
                self.inventory_repo.save(inventory)

            # Collect events and save
            uow.collect_events(booking)
            self.booking_repo.save(booking)
            # Events: BookingCancelled, InventoryDeallocated

        logger.info(f"Booking {booking.booking_number} cancelled successfully")

    def _calculate_refund(self, booking: Booking) -> Money:
        """
        Calculate refund amount based on cancellation policy

        TODO: Implement cancellation policy logic:
        - Flexible: 100% refund if cancelled 3+ days before
        - Moderate: 50% refund if cancelled 1-3 days before
        - Strict: 100% refund if cancelled 7+ days before
        """
        # For now, return full refund if payment was made
        if booking.payment_status.value == 'paid':
            return booking.final_price
        return Money(Decimal('0'), 'KZT')


class CheckInBookingHandler:
    """Handler for checking in guest"""

    def __init__(self, booking_repo):
        self.booking_repo = booking_repo

    def handle(self, command: CheckInBookingCommand):
        """Check in guest"""
        logger.info(f"Checking in booking {command.booking_id}")

        with DjangoUnitOfWork() as uow:
            booking = self.booking_repo.get_by_id(command.booking_id)
            if not booking:
                raise ValueError(f"Booking {command.booking_id} not found")

            # Check in (FSM transition CONFIRMED -> CHECKED_IN)
            booking.check_in()

            uow.collect_events(booking)
            self.booking_repo.save(booking)
            # Event: BookingCheckedIn

        logger.info(f"Booking {booking.booking_number} checked in successfully")


class CompleteBookingHandler:
    """Handler for completing booking (check out)"""

    def __init__(self, booking_repo):
        self.booking_repo = booking_repo

    def handle(self, command: CompleteBookingCommand):
        """Complete booking (check out)"""
        logger.info(f"Completing booking {command.booking_id}")

        with DjangoUnitOfWork() as uow:
            booking = self.booking_repo.get_by_id(command.booking_id)
            if not booking:
                raise ValueError(f"Booking {command.booking_id} not found")

            # Complete (FSM transition CHECKED_IN -> COMPLETED)
            booking.complete()

            uow.collect_events(booking)
            self.booking_repo.save(booking)
            # Event: BookingCompleted

        logger.info(f"Booking {booking.booking_number} completed successfully")