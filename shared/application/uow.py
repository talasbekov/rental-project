"""
Unit of Work Pattern

Manages database transactions and ensures that domain events
are published only after successful transaction commit.
"""

from abc import ABC, abstractmethod
from typing import List
import logging

from django.db import transaction

from shared.domain.base import DomainEvent

logger = logging.getLogger(__name__)


class AbstractUnitOfWork(ABC):
    """Abstract Unit of Work pattern"""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()

    @abstractmethod
    def commit(self):
        """Commit the transaction"""
        pass

    @abstractmethod
    def rollback(self):
        """Rollback the transaction"""
        pass

    @abstractmethod
    def collect_events(self, aggregate):
        """Collect events from aggregate root"""
        pass


class DjangoUnitOfWork(AbstractUnitOfWork):
    """
    Django implementation of Unit of Work

    Manages Django database transactions and ensures domain events
    are published after successful commit.

    Usage:
        with DjangoUnitOfWork() as uow:
            # Load aggregate
            booking = booking_repo.get_by_id(booking_id)

            # Execute domain logic
            booking.confirm_payment(payment_id)

            # Collect events
            uow.collect_events(booking)

            # Save changes
            booking_repo.save(booking)

            # Transaction commits here
        # Events are published after commit
    """

    def __init__(self):
        self._events: List[DomainEvent] = []
        self._transaction = None

    def __enter__(self):
        """Start database transaction"""
        self._transaction = transaction.atomic()
        self._transaction.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Complete or rollback transaction"""
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            if self._transaction:
                self._transaction.__exit__(exc_type, exc_val, exc_tb)

    def commit(self):
        """
        Commit changes and publish events

        Events are published using Django's transaction.on_commit()
        to ensure they're only sent after database commit succeeds.
        """
        logger.debug(f"Committing transaction with {len(self._events)} events")

        # Copy events before clearing
        events = self._events.copy()
        self._events.clear()

        # Schedule event publishing after commit
        if events:
            transaction.on_commit(lambda: self._publish_events(events))

    def rollback(self):
        """Rollback changes and discard events"""
        logger.warning(f"Rolling back transaction, discarding {len(self._events)} events")
        self._events.clear()

    def collect_events(self, aggregate):
        """
        Collect events from aggregate root

        Extracts all domain events from the aggregate and
        clears them from the aggregate.
        """
        if hasattr(aggregate, 'events'):
            new_events = aggregate.events
            if new_events:
                self._events.extend(new_events)
                aggregate.clear_events()
                logger.debug(
                    f"Collected {len(new_events)} events from "
                    f"{aggregate.__class__.__name__} (ID: {aggregate.id})"
                )

    def _publish_events(self, events: List[DomainEvent]):
        """
        Publish collected events to message bus

        Called after successful transaction commit.
        """
        from shared.application.message_bus import message_bus

        logger.info(f"Publishing {len(events)} domain events after commit")

        try:
            message_bus.publish_events(events)
        except Exception as e:
            logger.error(f"Error publishing events: {e}", exc_info=True)
            # Events are already committed to database
            # Failure to publish events should be handled by monitoring