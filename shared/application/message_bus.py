"""
Message Bus

Central hub for routing commands and events to their handlers.
Implements the Mediator pattern for decoupling components.
"""

from typing import Dict, List, Callable, Type, Any
import logging

from shared.domain.base import DomainEvent

logger = logging.getLogger(__name__)


class MessageBus:
    """
    Message bus for commands and events

    Commands: One handler per command (1:1)
    Events: Multiple handlers per event (1:N)
    """

    def __init__(self):
        self._event_handlers: Dict[Type[DomainEvent], List[Callable]] = {}
        self._command_handlers: Dict[Type, Callable] = {}

    def register_event_handler(
        self,
        event_type: Type[DomainEvent],
        handler: Callable[[DomainEvent], None]
    ):
        """
        Register an event handler

        Multiple handlers can be registered for the same event type.
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
        logger.debug(f"Registered event handler for {event_type.__name__}")

    def register_command_handler(
        self,
        command_type: Type,
        handler: Callable[[Any], Any]
    ):
        """
        Register a command handler

        Only one handler can be registered per command type.
        """
        if command_type in self._command_handlers:
            raise ValueError(
                f"Handler for {command_type.__name__} is already registered. "
                "Commands can have only one handler."
            )
        self._command_handlers[command_type] = handler
        logger.debug(f"Registered command handler for {command_type.__name__}")

    def handle_command(self, command: Any) -> Any:
        """
        Handle a command

        Returns the result from the command handler.
        Raises ValueError if no handler is registered.
        """
        command_type = type(command)
        handler = self._command_handlers.get(command_type)

        if not handler:
            raise ValueError(
                f"No handler registered for command {command_type.__name__}"
            )

        logger.info(f"Handling command: {command_type.__name__}")
        try:
            result = handler(command)
            logger.debug(f"Command {command_type.__name__} handled successfully")
            return result
        except Exception as e:
            logger.error(f"Error handling command {command_type.__name__}: {e}")
            raise

    def publish_events(self, events: List[DomainEvent]):
        """
        Publish domain events

        All registered handlers for each event type will be called.
        Errors in handlers are logged but don't stop other handlers.
        """
        for event in events:
            event_type = type(event)
            handlers = self._event_handlers.get(event_type, [])

            if not handlers:
                logger.warning(f"No handlers registered for event {event_type.__name__}")
                continue

            logger.info(f"Publishing event: {event_type.__name__} (ID: {event.event_id})")

            for handler in handlers:
                try:
                    handler(event)
                    logger.debug(f"Event {event_type.__name__} handled by {handler.__name__}")
                except Exception as e:
                    logger.error(
                        f"Error in event handler {handler.__name__} "
                        f"for event {event_type.__name__}: {e}",
                        exc_info=True
                    )
                    # Don't raise - other handlers should still run


# Global message bus instance
message_bus = MessageBus()