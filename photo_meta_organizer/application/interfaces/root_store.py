"""Where the library keeps its roots (ADR-003 R11, ticket 09)."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from photo_meta_organizer.application.roots import Root


class RootStore(Protocol):
    """The folders to scan on start, plus the one-off answer about suggesting them."""

    def list_roots(self) -> "list[Root]":
        """Every root, oldest first."""
        ...

    def add_root(self, path: str) -> "Root":
        """Remember ``path`` (already absolute). Adding a known root returns it unchanged."""
        ...

    def remove_root(self, path: str) -> bool:
        """Forget a root; its photos stay. False if ``path`` was not a root."""
        ...

    def observed_folders(self) -> dict[str, int]:
        """Folder -> number of present Files directly in it, from the recorded paths."""
        ...

    def suggestions_dismissed(self) -> bool:
        """Whether the user skipped the suggested roots."""
        ...

    def dismiss_suggestions(self) -> None:
        """Remember that the user skipped them, so they are not offered again."""
        ...
