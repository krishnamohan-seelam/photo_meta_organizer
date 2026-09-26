"""TinyDB-based implementation of CollectionRepository.

Shares the same open ``TinyDB`` instance as a sibling ``TinyDBRepository`` (pass
``repo.db``), so both read and write the same JSON file through one handle.
"""

import logging
from typing import List, Optional

from tinydb import Query, TinyDB

from photo_meta_organizer.application.interfaces.collection_repository import CollectionRecord
from photo_meta_organizer.domain.datetimes import utc_now_naive

logger = logging.getLogger(__name__)


class TinyDBCollectionRepository:
    """TinyDB-backed repository for named photo collections."""

    def __init__(self, db: TinyDB) -> None:
        self._table = db.table("collections")

    @staticmethod
    def _to_record(doc: dict) -> CollectionRecord:
        return CollectionRecord(
            name=doc.get("name", ""),
            description=doc.get("description", ""),
            photo_hashes=list(doc.get("photo_hashes", [])),
            updated_at=doc.get("updated_at", ""),
        )

    def list_all(self) -> List[CollectionRecord]:
        return [self._to_record(doc) for doc in self._table.all()]

    def get(self, name: str) -> Optional[CollectionRecord]:
        q = Query()
        results = self._table.search(q.name == name)
        return self._to_record(results[0]) if results else None

    def save(self, name: str, photo_hashes: List[str], description: str = "") -> CollectionRecord:
        q = Query()
        doc = {
            "name": name,
            "description": description,
            "photo_hashes": list(photo_hashes),
            "updated_at": utc_now_naive().isoformat(),
        }
        self._table.upsert(doc, q.name == name)
        return self._to_record(doc)

    def delete(self, name: str) -> bool:
        q = Query()
        removed = self._table.remove(q.name == name)
        return bool(removed)

    def remove_photo_from_all(self, file_hash: str) -> int:
        """Strip ``file_hash`` from every collection that references it."""
        touched = 0

        def strip(doc: dict) -> None:
            nonlocal touched
            hashes = doc.get("photo_hashes", [])
            if file_hash in hashes:
                doc["photo_hashes"] = [h for h in hashes if h != file_hash]
                touched += 1

        q = Query()
        self._table.update(strip, q.photo_hashes.test(lambda hashes: file_hash in (hashes or [])))
        return touched
