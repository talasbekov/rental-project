"""
Common Value Objects

Value objects used across multiple domains:
- Money: Represents monetary amounts with currency
- DateRange: Represents a range of dates (check-in to check-out)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from shared.domain.base import ValueObject


@dataclass(frozen=True)
class Money(ValueObject):
    """
    Money value object

    Represents a monetary amount with currency.
    Immutable and supports arithmetic operations.
    """
    amount: Decimal
    currency: str = 'KZT'

    def __post_init__(self):
        # Validation
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")
        if not self.currency:
            raise ValueError("Currency is required")
        if self.currency not in ['KZT', 'USD', 'EUR', 'RUB']:
            raise ValueError(f"Unsupported currency: {self.currency}")

    def __add__(self, other: 'Money') -> 'Money':
        """Add two money objects"""
        if not isinstance(other, Money):
            raise TypeError("Can only add Money to Money")
        if self.currency != other.currency:
            raise ValueError(f"Cannot add different currencies: {self.currency} and {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: 'Money') -> 'Money':
        """Subtract two money objects"""
        if not isinstance(other, Money):
            raise TypeError("Can only subtract Money from Money")
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract different currencies: {self.currency} and {other.currency}")
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: float) -> 'Money':
        """Multiply money by a factor"""
        if not isinstance(factor, (int, float, Decimal)):
            raise TypeError("Can only multiply Money by number")
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __truediv__(self, factor: float) -> 'Money':
        """Divide money by a factor"""
        if not isinstance(factor, (int, float, Decimal)):
            raise TypeError("Can only divide Money by number")
        if factor == 0:
            raise ValueError("Cannot divide by zero")
        return Money(self.amount / Decimal(str(factor)), self.currency)

    def __str__(self):
        return f"{self.amount:,.2f} {self.currency}"

    def __repr__(self):
        return f"Money({self.amount}, '{self.currency}')"


@dataclass(frozen=True)
class DateRange(ValueObject):
    """
    Date range value object

    Represents a range from start_date (inclusive) to end_date (exclusive).
    Used for booking periods, availability checks, etc.
    """
    start_date: date
    end_date: date

    def __post_init__(self):
        # Validation
        if self.start_date >= self.end_date:
            raise ValueError(f"Start date ({self.start_date}) must be before end date ({self.end_date})")

    def overlaps_with(self, other: 'DateRange') -> bool:
        """
        Check if this range overlaps with another

        Two ranges overlap if they share any dates.
        Note: end_date is exclusive, so adjacent ranges don't overlap.

        Examples:
            - DateRange(25, 28) overlaps with DateRange(27, 30) -> True
            - DateRange(25, 28) overlaps with DateRange(28, 31) -> False (adjacent)
        """
        if not isinstance(other, DateRange):
            raise TypeError("Can only check overlap with another DateRange")

        # Overlap formula: start1 < end2 AND end1 > start2
        return (self.start_date < other.end_date and
                self.end_date > other.start_date)

    def contains(self, check_date: date) -> bool:
        """
        Check if a date is within this range

        Note: start_date is inclusive, end_date is exclusive
        """
        return self.start_date <= check_date < self.end_date

    def __len__(self) -> int:
        """
        Return the number of days (nights) in this range

        This is the number of nights for a booking.
        """
        return (self.end_date - self.start_date).days

    def __str__(self):
        return f"{self.start_date.strftime('%d.%m.%Y')} - {self.end_date.strftime('%d.%m.%Y')}"

    def __repr__(self):
        return f"DateRange({self.start_date}, {self.end_date})"