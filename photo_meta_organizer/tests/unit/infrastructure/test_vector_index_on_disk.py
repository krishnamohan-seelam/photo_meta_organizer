"""Ticket 16 (ADR-003 R6): the vector index survives a restart as a memory-mapped .npy pair.

Each model has an ``embeddings_generation`` counter, bumped in the same transaction as any write
to its embeddings (cascade deletes included). The pair's headers carry the generation and the
library's id; a file that does not match is rebuilt from SQLite, never trusted.
"""

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from photo_meta_organizer.application.interfaces.vector_index import VectorIndex
from photo_meta_organizer.domain.analysis import Embedding
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories import brute_force_vector_index
from photo_meta_organizer.infrastructure.repositories.brute_force_vector_index import (
    BruteForceVectorIndex,
)
from photo_meta_organizer.infrastructure.repositories.migrations import MIGRATIONS, migrate
from photo_meta_organizer.infrastructure.repositories.sqlite_analysis_repository import (
    SqliteAnalysisRepository,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository

M = "clip-test"


def _photo(hash_: str) -> ImageMetadata:
    return ImageMetadata(
        file_hash=hash_,
        file_info=ImageFileInfo(
            name=f"{hash_}.jpg", path=f"/photos/{hash_}.jpg", size_bytes=10, mime_type="image/jpeg"
        ),
        dimensions=ImageDimensions(width=10, height=10),
        exif=ImageExifData(),
    )


def _emb(hash_: str, *vector: float, model: str = M) -> Embedding:
    return Embedding(file_hash=hash_, model_id=model, vector=vector)


def _generation(repo: SqliteRepository, model: str = M) -> int:
    row = repo.connection.execute(
        "SELECT generation FROM embedding_generations WHERE model_id = ?", (model,)
    ).fetchone()
    return 0 if row is None else int(row[0])


class _Library:
    """A library file plus the analysis store over it, reopened like an app restart."""

    def __init__(self, db: Path, index_dir: Path) -> None:
        self.db = db
        self.index_dir = index_dir
        self.photos = SqliteRepository(str(db))
        self.analysis = SqliteAnalysisRepository(
            self.photos.connection,
            self.photos.lock,
            # Every rebuild is saved, so a test can look at the files after each write.
            BruteForceVectorIndex(
                self.photos.connection, self.photos.lock, index_dir, save_interval=0
            ),
        )

    def restart(self) -> "_Library":
        self.photos.close()
        return _Library(self.db, self.index_dir)

    def ranked(self, *vector: float) -> list[str]:
        return [h.file_hash for h in self.analysis.nearest(vector, k=10, model_id=M)]


@pytest.fixture
def library(tmp_path: Path):
    lib = _Library(tmp_path / "photos.db", tmp_path / "vector-index")
    lib.photos.save_many([_photo("east"), _photo("north"), _photo("west")])
    lib.analysis.save_embeddings(
        [_emb("east", 1.0, 0.0), _emb("north", 0.0, 1.0), _emb("west", -1.0, 0.1)]
    )
    yield lib
    lib.photos.close()


def _no_database_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object) -> None:
        raise AssertionError("the index was rebuilt from SQLite")

    monkeypatch.setattr(brute_force_vector_index, "_read_rows", refuse)


def test_the_index_satisfies_the_port(library) -> None:
    assert isinstance(
        BruteForceVectorIndex(library.photos.connection, library.photos.lock), VectorIndex
    )


class TestGeneration:
    def test_every_embedding_write_bumps_only_that_models_generation(self, library) -> None:
        first = _generation(library.photos)
        assert first > 0
        library.analysis.save_embeddings([_emb("east", 0.5, 0.5)])
        second = _generation(library.photos)
        assert second > first

        library.analysis.save_embeddings([_emb("east", 1.0, 0.0, model="other")])
        assert _generation(library.photos) == second
        library.analysis.clear_embeddings(M)
        assert _generation(library.photos) > second
        assert _generation(library.photos, "other") > 0

    def test_a_cascade_delete_of_the_asset_bumps_it(self, library) -> None:
        before = _generation(library.photos)
        library.photos.delete_by_path("/photos/east.jpg")
        assert _generation(library.photos) > before

    def test_a_rolled_back_write_does_not(self, library) -> None:
        before = _generation(library.photos)
        conn = library.photos.connection
        with pytest.raises(RuntimeError), conn:
            conn.execute("DELETE FROM photo_embeddings WHERE model_id = ?", (M,))
            raise RuntimeError("abort")
        assert _generation(library.photos) == before

    def test_an_existing_library_gains_counters_for_its_models(self, tmp_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_path / "old.db"))
        migrate(conn, str(tmp_path / "old.db"), MIGRATIONS[:7])
        conn.executescript(
            "INSERT INTO assets (file_hash, size_bytes, mime_type, width, height, extracted_at) "
            "VALUES ('a', 10, 'image/jpeg', 10, 10, '2024-01-01');"
            "INSERT INTO photo_embeddings VALUES ('a', 'clip-test', 2, x'0000803f00000000', '');"
        )
        conn.commit()
        migrate(conn, str(tmp_path / "old.db"))
        rows = conn.execute("SELECT model_id, generation FROM embedding_generations").fetchall()
        library_id = conn.execute(
            "SELECT value FROM library_state WHERE key = 'library_id'"
        ).fetchone()
        conn.close()
        assert rows == [("clip-test", 1)]
        assert library_id is not None and len(library_id[0]) == 32


class TestOnDisk:
    def test_a_restart_maps_the_saved_index_instead_of_reading_sqlite(
        self, library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        expected = library.ranked(1.0, 0.0)
        assert sorted(p.name for p in library.index_dir.iterdir()) == [
            "clip-test-2.hashes.npy",
            "clip-test-2.vectors.npy",
        ]
        restarted = library.restart()
        _no_database_reads(monkeypatch)
        assert restarted.ranked(1.0, 0.0) == expected == ["east", "north", "west"]
        restarted.photos.close()

    def test_a_write_since_the_index_was_saved_rebuilds_it(self, library) -> None:
        library.ranked(1.0, 0.0)
        library.photos.save(_photo("south"))
        library.analysis.save_embeddings([_emb("south", 0.9, -0.1)])
        restarted = library.restart()
        assert restarted.ranked(1.0, 0.0)[:2] == ["east", "south"]
        restarted.photos.close()

    def test_a_write_in_the_same_session_is_seen_by_the_next_search(self, library) -> None:
        assert library.ranked(1.0, 0.0)[0] == "east"
        library.photos.delete_by_path("/photos/east.jpg")
        assert library.ranked(1.0, 0.0) == ["north", "west"]

    def test_the_index_of_another_library_is_not_used(self, library, tmp_path: Path) -> None:
        library.ranked(1.0, 0.0)
        other = _Library(tmp_path / "other.db", library.index_dir)
        other.photos.save_many([_photo("x"), _photo("y"), _photo("z")])
        # Same model, same number of writes: only the library id tells the files apart.
        other.analysis.save_embeddings(
            [_emb("x", 1.0, 0.0), _emb("y", 0.0, 1.0), _emb("z", -1.0, 0.1)]
        )
        assert _generation(other.photos) == _generation(library.photos)
        assert other.ranked(1.0, 0.0) == ["x", "y", "z"]
        other.photos.close()

    def test_a_pair_from_different_generations_is_rebuilt(self, library) -> None:
        library.ranked(1.0, 0.0)
        old_hashes = library.index_dir / "clip-test-2.hashes.npy"
        kept = old_hashes.read_bytes()
        library.photos.save(_photo("south"))
        library.analysis.save_embeddings([_emb("south", 0.9, -0.1)])
        library.ranked(1.0, 0.0)
        old_hashes.write_bytes(kept)
        restarted = library.restart()
        assert restarted.ranked(1.0, 0.0)[:2] == ["east", "south"]
        restarted.photos.close()

    @pytest.mark.parametrize("damage", [b"", b"not an npy file", b"\x93NUMPY\x01\x00\xff\xff"])
    def test_a_damaged_file_is_rebuilt(self, library, damage: bytes) -> None:
        library.ranked(1.0, 0.0)
        (library.index_dir / "clip-test-2.vectors.npy").write_bytes(damage)
        restarted = library.restart()
        assert restarted.ranked(1.0, 0.0) == ["east", "north", "west"]
        restarted.photos.close()

    def test_the_saved_vectors_are_the_unit_vectors(self, library) -> None:
        library.ranked(1.0, 0.0)
        restarted = library.restart()
        hits = restarted.analysis.nearest([3.0, 4.0], k=1, model_id=M)
        assert hits[0].file_hash == "north"
        assert hits[0].score == pytest.approx(0.8, abs=1e-6)
        restarted.photos.close()

    def test_an_unusable_directory_still_searches_from_memory(self, tmp_path: Path) -> None:
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x")
        lib = _Library(tmp_path / "photos.db", blocker)
        lib.photos.save(_photo("a"))
        lib.analysis.save_embeddings([_emb("a", 1.0, 0.0)])
        assert lib.ranked(1.0, 0.0) == ["a"]
        lib.photos.close()

    def test_nothing_is_written_without_a_directory_or_without_embeddings(
        self, tmp_path: Path
    ) -> None:
        lib = _Library(tmp_path / "photos.db", tmp_path / "vector-index")
        assert lib.ranked(1.0, 0.0) == []
        assert not (tmp_path / "vector-index").exists()
        lib.photos.close()

    def test_the_vectors_file_is_a_plain_npy_matrix(self, library) -> None:
        library.ranked(1.0, 0.0)
        matrix = brute_force_vector_index.read_index_file(
            library.index_dir / "clip-test-2.vectors.npy"
        )
        assert matrix is not None
        header, vectors = matrix
        assert header["generation"] == _generation(library.photos)
        assert vectors.shape == (3, 2) and vectors.dtype == np.dtype("<f4")


def _backup(library: _Library, target: Path) -> None:
    connection = sqlite3.connect(str(target))
    library.photos.connection.backup(connection)
    connection.close()


def test_a_copy_that_reaches_the_saved_generation_with_other_content_is_rebuilt(
    library, tmp_path: Path
) -> None:
    """A backup restored, or a copy opened with --db, keeps the library id; one write in each
    brings both to the same generation and the same row count with different vectors."""
    _backup(library, tmp_path / "copy.db")
    library.photos.save(_photo("south"))
    library.analysis.save_embeddings([_emb("south", 0.9, -0.1)])
    library.ranked(1.0, 0.0)
    copy = _Library(tmp_path / "copy.db", library.index_dir)
    copy.photos.save(_photo("ahead"))
    copy.analysis.save_embeddings([_emb("ahead", 1.0, 0.05)])
    assert _generation(copy.photos) == _generation(library.photos)
    assert copy.ranked(1.0, 0.0) == ["east", "ahead", "north", "west"]
    copy.photos.close()


def test_rebuilds_in_one_session_are_saved_at_most_once_per_interval(tmp_path: Path) -> None:
    now = [0.0]
    photos = SqliteRepository(str(tmp_path / "photos.db"))
    index = BruteForceVectorIndex(
        photos.connection, photos.lock, tmp_path / "index", save_interval=300, clock=lambda: now[0]
    )
    analysis = SqliteAnalysisRepository(photos.connection, photos.lock, index)
    vectors = tmp_path / "index" / "clip-test-2.vectors.npy"

    def saved_generation() -> int:
        read = brute_force_vector_index.read_index_file(vectors)
        assert read is not None
        return int(read[0]["generation"])

    def search_at(seconds: float, hash_: str, x: float) -> int:
        """Write one embedding, search at ``seconds``, return the generation then current."""
        analysis.save_embeddings([_emb(hash_, 1.0, x)])
        now[0] = seconds
        assert analysis.nearest([1.0, 0.0], k=3, model_id=M)[0].file_hash == "a"
        return _generation(photos)

    photos.save_many([_photo("a"), _photo("b"), _photo("c")])
    first = search_at(0.0, "a", 0.0)
    assert saved_generation() == first  # the session's first rebuild is saved
    search_at(299.0, "b", 1.0)
    assert saved_generation() == first  # too soon after the last save
    third = search_at(300.0, "c", 2.0)
    assert saved_generation() == third
    photos.close()


def test_a_copy_of_the_library_reuses_the_index(
    library, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backup restored over the library is the same library: same id, same generation."""
    library.ranked(1.0, 0.0)
    _backup(library, tmp_path / "copy.db")
    copy = _Library(tmp_path / "copy.db", library.index_dir)
    _no_database_reads(monkeypatch)
    assert copy.ranked(1.0, 0.0) == ["east", "north", "west"]
    copy.photos.close()
