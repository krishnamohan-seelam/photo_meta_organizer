"""Collection (album) repository interface.

Split out of ``ImageMetadataRepository`` (PMO-07): collections are a distinct
aggregate from photo metadata, and giving them their own port lets an
implementation enforce (or, for TinyDB, emulate) cascading cleanup when a
photo referenced by a collection is deleted.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class CollectionRecord:
    """A named, curated set of photo hashes."""

    name: str
    description: str = ""
    photo_hashes: List[str] = field(default_factory=list)
    updated_at: str = ""


@runtime_checkable
class CollectionRepository(Protocol):
    """Protocol defining the contract for collection persistence."""

    def list_all(self) -> List[CollectionRecord]:
        """Return every stored collection."""
        ...

    def get(self, name: str) -> Optional[CollectionRecord]:
        """Return the collection named ``name``, or ``None``."""
        ...

    def save(self, name: str, photo_hashes: List[str], description: str = "") -> CollectionRecord:
        """Create or update a named collection (upsert semantics)."""
        ...

    def delete(self, name: str) -> bool:
        """Delete a collection by name. Returns ``False`` if it did not exist."""
        ...

    def remove_photo_from_all(self, file_hash: str) -> int:
        """Strip ``file_hash`` from every collection that references it.

        Called when a photo is deleted independently of its collections, so a
        collection never keeps a dangling hash. Returns the number of
        collections touched.
        """
        ...
