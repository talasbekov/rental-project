"""
Base Domain Classes

This module provides the foundational building blocks for Domain-Driven Design:
- Entity: Objects with unique identity
- ValueObject: Immutable objects compared by value
- Aggregate: Consistency boundaries with domain events
- DomainEvent: Events that represent something that happened
"""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from uuid import UUID, uuid4


@dataclass
class Entity(ABC):
    """
    Base class for all entities

    Entities have unique identity and are mutable.
    Two entities are equal if their IDs are equal.
    """
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)


@dataclass(frozen=True)
class ValueObject(ABC):
    """
    Base class for value objects

    Value objects are immutable and have no identity.
    Two value objects are equal if all their attributes are equal.
    """
    pass


@dataclass
class Aggregate(Entity):
    """
    Base class for aggregate roots

    Aggregates are the consistency boundaries in DDD.
    They collect domain events that will be published after successful transaction.
    """
    _events: List['DomainEvent'] = field(default_factory=list, repr=False, init=False)

    def add_event(self, event: 'DomainEvent'):
        """Add a domain event to be published"""
        self._events.append(event)

    def clear_events(self):
        """Clear all collected events (called after publishing)"""
        self._events.clear()

    @property
    def events(self) -> List['DomainEvent']:
        """Get copy of collected events"""
        return self._events.copy()


@dataclass
class DomainEvent:
    """
    Base class for domain events

    Domain events represent something that happened in the domain.
    They are used to communicate between bounded contexts.
    """
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=datetime.now)
    aggregate_id: UUID = None

    def to_dict(self) -> dict:
        """Convert event to dictionary for serialization"""
        return {
            'event_id': str(self.event_id),
            'event_type': self.__class__.__name__,
            'occurred_at': self.occurred_at.isoformat(),
            'aggregate_id': str(self.aggregate_id) if self.aggregate_id else None,
        }