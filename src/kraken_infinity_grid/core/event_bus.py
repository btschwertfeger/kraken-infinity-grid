# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#


from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Event:
    """Base event class"""

    type: str
    data: dict[str, Any]


class EventBus:
    """Central event bus for communication between components"""

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}

    def subscribe(self, event_type: str, callback: Callable[[Event], None]) -> None:
        """Subscribe to an event type"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers"""
        if event.type not in self._subscribers:
            return

        for callback in self._subscribers[event.type]:
            callback(event)
