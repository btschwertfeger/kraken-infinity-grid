# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

"""Unit tests for the StateMachine class."""

from unittest.mock import Mock

import pytest

from kraken_infinity_grid.core.state_machine import StateMachine, States


@pytest.fixture
def state_machine() -> StateMachine:
    """Create a fresh StateMachine instance for each test"""
    return StateMachine()


def test_initialization_default(state_machine: StateMachine) -> None:
    """Test default initialization"""
    assert state_machine.state == States.INITIALIZING
    assert state_machine.facts["ready_to_trade"] is False
    assert state_machine.facts["ticker_channel_connected"] is False
    assert state_machine.facts["executions_channel_connected"] is False


def test_initialization_custom() -> None:
    """Test custom initialization with specific state"""
    sm = StateMachine(initial_state=States.RUNNING)
    assert sm.state == States.RUNNING


def test_valid_state_transitions(state_machine: StateMachine) -> None:
    """Test valid state transitions"""
    # INITIALIZING -> RUNNING
    state_machine.transition_to(States.RUNNING)
    assert state_machine.state == States.RUNNING

    # RUNNING -> ERROR
    state_machine.transition_to(States.ERROR)
    assert state_machine.state == States.ERROR

    # ERROR -> RUNNING (recovery)
    state_machine.transition_to(States.RUNNING)
    assert state_machine.state == States.RUNNING

    # RUNNING -> SHUTDOWN_REQUESTED
    state_machine.transition_to(States.SHUTDOWN_REQUESTED)
    assert state_machine.state == States.SHUTDOWN_REQUESTED


def test_invalid_transition_shutdown_to_running() -> None:
    """Test invalid transition from SHUTDOWN_REQUESTED to RUNNING"""
    sm = StateMachine(initial_state=States.SHUTDOWN_REQUESTED)
    with pytest.raises(ValueError, match=r"Invalid state transition.*"):
        sm.transition_to(States.RUNNING)


def test_invalid_transition_initializing_to_invalid_state(
    state_machine: StateMachine,
) -> None:
    """Test transition to non-existent state"""
    with pytest.raises(ValueError, match=r"Invalid state transition from.*"):
        state_machine.transition_to("INVALID_STATE")  # type: ignore[arg-type]


def test_same_state_transition(state_machine: StateMachine) -> None:
    """Test transition to the same state (should be no-op)"""
    state_machine.transition_to(States.RUNNING)
    # Transitioning to the same state should not raise an error
    state_machine.transition_to(States.RUNNING)
    assert state_machine.state == States.RUNNING


def test_facts_getter(state_machine: StateMachine) -> None:
    """Test getting facts"""
    facts = state_machine.facts
    assert facts["ready_to_trade"] is False
    assert facts["ticker_channel_connected"] is False
    assert facts["executions_channel_connected"] is False


def test_facts_setter_single(state_machine: StateMachine) -> None:
    """Test setting a single fact"""
    state_machine.facts = {"ready_to_trade": True}
    assert state_machine.facts["ready_to_trade"] is True
    # Other facts should remain unchanged
    assert state_machine.facts["ticker_channel_connected"] is False


def test_facts_setter_multiple(state_machine: StateMachine) -> None:
    """Test setting multiple facts at once"""
    state_machine.facts = {
        "ticker_channel_connected": True,
        "executions_channel_connected": True,
    }
    assert state_machine.facts["ticker_channel_connected"] is True
    assert state_machine.facts["executions_channel_connected"] is True
    assert state_machine.facts["ready_to_trade"] is False  # Unchanged


def test_facts_setter_invalid_key(state_machine: StateMachine) -> None:
    """Test setting a fact with an invalid key"""
    with pytest.raises(KeyError, match=r".*'non_existent_fact' does not exist.*"):
        state_machine.facts = {"non_existent_fact": True}


def test_register_and_execute_callback(state_machine: StateMachine) -> None:
    """Test registering and executing a callback"""
    mock_callback = Mock()
    state_machine.register_callback(States.RUNNING, mock_callback)

    # Before transition - callback shouldn't be called
    mock_callback.assert_not_called()

    # After transition - callback should be called once
    state_machine.transition_to(States.RUNNING)
    mock_callback.assert_called_once()


def test_multiple_callbacks_for_state(state_machine: StateMachine) -> None:
    """Test registering and executing multiple callbacks for the same state"""
    callback1 = Mock()
    callback2 = Mock()

    state_machine.register_callback(States.RUNNING, callback1)
    state_machine.register_callback(States.RUNNING, callback2)

    state_machine.transition_to(States.RUNNING)

    callback1.assert_called_once()
    callback2.assert_called_once()


def test_callbacks_for_different_states(state_machine: StateMachine) -> None:
    """Test callbacks for different states are called appropriately"""
    running_cb = Mock()
    error_cb = Mock()

    state_machine.register_callback(States.RUNNING, running_cb)
    state_machine.register_callback(States.ERROR, error_cb)

    state_machine.transition_to(States.RUNNING)
    running_cb.assert_called_once()
    error_cb.assert_not_called()

    running_cb.reset_mock()

    state_machine.transition_to(States.ERROR)
    running_cb.assert_not_called()
    error_cb.assert_called_once()


def test_fact_persistence_across_transitions(state_machine: StateMachine) -> None:
    """Test that facts are persistent across state transitions"""
    # Set initial facts
    state_machine.facts = {"ready_to_trade": True}

    # Transition states
    state_machine.transition_to(States.RUNNING)
    assert state_machine.facts["ready_to_trade"] is True

    state_machine.transition_to(States.ERROR)
    assert state_machine.facts["ready_to_trade"] is True

    state_machine.transition_to(States.SHUTDOWN_REQUESTED)
    assert state_machine.facts["ready_to_trade"] is True
