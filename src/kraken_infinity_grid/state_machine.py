# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

"""State machine for the Kraken Infinity Grid trading bot."""

from enum import Enum, auto
from typing import Callable, Self


class States(Enum):
    """Represents the state of the trading bot"""

    INITIALIZING = auto()
    RUNNING = auto()
    SHUTDOWN_REQUESTED = auto()
    ERROR = auto()


class StateMachine:
    """Manages state transitions of the algorithm"""

    def __init__(
        self: Self,
        initial_state: States = States.INITIALIZING,
    ) -> None:
        self._state: States = initial_state
        self._transitions = self._define_transitions()
        self._callbacks: dict[States, list[Callable]] = {}
        self._facts: dict = {
            "ready_to_trade": False,
            "ticker_channel_connected": False,
            "executions_channel_connected": False,
        }

    def _define_transitions(self: Self) -> dict[States, list[States]]:
        return {
            States.INITIALIZING: [
                States.RUNNING,
                States.SHUTDOWN_REQUESTED,
                States.ERROR,
            ],
            States.RUNNING: [States.ERROR, States.SHUTDOWN_REQUESTED],
            States.ERROR: [States.RUNNING, States.SHUTDOWN_REQUESTED],
            States.SHUTDOWN_REQUESTED: [],
        }

    def transition_to(self: Self, new_state: States) -> None:
        """Attempt to transition to a new state"""
        if new_state == self._state:
            return

        if new_state not in self._transitions[self._state]:
            raise ValueError(
                f"Invalid state transition from {self._state} to {new_state}",
            )

        self._state = new_state

        # Execute callbacks for this transition if any
        if new_state in self._callbacks:
            for callback in self._callbacks[new_state]:
                callback()

    @property
    def state(self: Self) -> States:
        return self._state

    @property
    def facts(self: Self) -> dict[str, bool]:
        """Return the current facts of the state machine"""
        return self._facts

    @facts.setter
    def facts(self: Self, new_facts: dict[str, bool]) -> None:
        """Update the facts of the state machine"""
        for key, value in new_facts.items():
            if key in self._facts:
                self._facts[key] = value
            else:
                raise KeyError(f"Fact '{key}' does not exist in the state machine.")

    def register_callback(
        self: Self,
        to_state: States,
        callback: Callable,
    ) -> None:
        """Register a callback to be executed on specific state transitions"""
        if to_state not in self._callbacks:
            self._callbacks[to_state] = []
        self._callbacks[to_state].append(callback)
