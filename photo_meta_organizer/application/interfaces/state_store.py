"""Small named values the library remembers between runs (ADR-003, tickets 09 and 11)."""

from typing import Protocol


class StateStore(Protocol):
    """A key/value store in the library: settings the user chose and one-off answers."""

    def get(self, key: str) -> str | None:
        """The stored value, or ``None`` if the key was never set."""
        ...

    def set(self, key: str, value: str) -> None:
        """Store ``value`` under ``key``, replacing any earlier one."""
        ...
