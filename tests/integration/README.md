# Integration and System TEsts

This directory contains integration and system tests for the project. They
mainly focus on mocking the external dependencies (python-kraken-sdk) in order
to simulate the real-world exchange and the behavior of the system on new ticker
events, executions and so on.

**Characteristics:**

- Mocks external dependencies (Kraken API)
- Tests multiple components working together (Focuses on component interactions)
- Tests full system behavior (Verifies business logic flows end-to-end)
- Verifies component interactions (Uses mocks only for external systems)
- Tests database interactions (Uses in-memory database)
- Tests message flow and state changes (Validates state changes)

**It does not include the following:**

- Live tests against the live Kraken API
- Tests against the CLI (which would be E2E)
- Input validation (as the input is fixed)
