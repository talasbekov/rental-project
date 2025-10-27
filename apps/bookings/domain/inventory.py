"""
Inventory Aggregate

This is the CRITICAL aggregate for preventing double bookings.
All date allocations MUST go through this aggregate.

The Inventory aggregate is the consistency boundary that ensures
no two bookings can overlap for the same property.

Strategy (Defense in Depth):
1. Domain validation: can_allocate() checks for overlaps
2. Database constraint: PostgreSQL EXCLUDE constraint
3. Pessimistic locking: SELECT FOR UPDATE in transactions
"""

from dataclasses import dataclass, field
from typing import List
from uuid import UUID, uuid4

from shared.domain.base import Aggregate
from shared.domain.value_objects import DateRange


@dataclass
class Allocation:
    """
    Allocation entity - represents a booked date range

    An allocation reserves specific dates for a booking.
    Multiple allocations can exist for a property, but they cannot overlap.
    """
    id: UUID = field(default_factory=uuid4)
    booking_id: UUID | None = None
    dates: DateRange = None
    quantity: int = 1  # For future: hotels with multiple rooms of same type

    def __post_init__(self):
        if not self.dates:
            raise ValueError("Allocation must have dates")
        if self.quantity < 1:
            raise ValueError("Allocation quantity must be at least 1")


@dataclass
class Inventory(Aggregate):
    """
    Inventory Aggregate Root

    This aggregate manages date availability for a property.
    It is the consistency boundary for preventing double bookings.

    Key invariants:
    - No overlapping allocations for the same property
    - All allocations must have valid date ranges
    - Quantity must be positive

    Usage:
        # Load inventory for property (with SELECT FOR UPDATE lock)
        inventory = inventory_repo.get_by_property_id(property_id, lock=True)

        # Check if dates can be allocated
        if inventory.can_allocate(date_range):
            # Allocate dates
            allocation = inventory.allocate(booking_id, date_range)
            inventory_repo.save(inventory)
        else:
            raise ValueError("Dates not available")
    """

    property_id: UUID
    allocations: List[Allocation] = field(default_factory=list)

    def can_allocate(self, dates: DateRange) -> bool:
        """
        Check if dates can be allocated (no overlaps)

        Returns True if dates are available, False otherwise.
        This is the first line of defense against double bookings.
        """
        for allocation in self.allocations:
            if allocation.dates.overlaps_with(dates):
                return False
        return True

    def allocate(self, booking_id: UUID, dates: DateRange, quantity: int = 1) -> Allocation:
        """
        Allocate dates for a booking

        This method enforces the critical business rule:
        NO TWO BOOKINGS CAN HAVE OVERLAPPING DATES FOR THE SAME PROPERTY

        Args:
            booking_id: The booking reserving these dates
            dates: The date range to allocate
            quantity: Number of units (for hotels, default=1)

        Returns:
            The created allocation

        Raises:
            ValueError: If dates are not available (overlap detected)
        """
        # Validate availability (domain-level check)
        if not self.can_allocate(dates):
            # Find which allocation overlaps
            overlapping = None
            for alloc in self.allocations:
                if alloc.dates.overlaps_with(dates):
                    overlapping = alloc
                    break

            raise ValueError(
                f"Dates {dates} are not available for property {self.property_id}. "
                f"Overlaps with existing allocation {overlapping.id} "
                f"(booking {overlapping.booking_id})"
            )

        # Create allocation
        allocation = Allocation(
            id=uuid4(),
            booking_id=booking_id,
            dates=dates,
            quantity=quantity
        )

        # Add to inventory
        self.allocations.append(allocation)

        # Emit domain event
        from apps.bookings.domain.events import InventoryAllocated

        self.add_event(InventoryAllocated(
            aggregate_id=self.id,
            property_id=self.property_id,
            allocation_id=allocation.id,
            booking_id=booking_id,
            dates=dates
        ))

        return allocation

    def deallocate(self, booking_id: UUID):
        """
        Remove allocation for a booking

        This is called when a booking is cancelled, freeing up the dates.

        Args:
            booking_id: The booking whose allocation should be removed

        Raises:
            ValueError: If no allocation found for this booking
        """
        # Find allocation for this booking
        allocation = next(
            (a for a in self.allocations if a.booking_id == booking_id),
            None
        )

        if not allocation:
            raise ValueError(
                f"No allocation found for booking {booking_id} "
                f"in property {self.property_id}"
            )

        # Remove allocation
        self.allocations.remove(allocation)

        # Emit domain event
        from apps.bookings.domain.events import InventoryDeallocated

        self.add_event(InventoryDeallocated(
            aggregate_id=self.id,
            property_id=self.property_id,
            allocation_id=allocation.id,
            booking_id=booking_id
        ))

    def get_allocation(self, booking_id: UUID) -> Allocation | None:
        """Get allocation for a specific booking"""
        return next(
            (a for a in self.allocations if a.booking_id == booking_id),
            None
        )

    def get_allocations_for_period(self, dates: DateRange) -> List[Allocation]:
        """Get all allocations that overlap with given period"""
        return [
            a for a in self.allocations
            if a.dates.overlaps_with(dates)
        ]

    @property
    def total_allocations(self) -> int:
        """Total number of allocations"""
        return len(self.allocations)

    def __str__(self):
        return f"Inventory(property={self.property_id}, allocations={len(self.allocations)})"

    def __repr__(self):
        return (
            f"Inventory(id={self.id}, property_id={self.property_id}, "
            f"allocations_count={len(self.allocations)})"
        )