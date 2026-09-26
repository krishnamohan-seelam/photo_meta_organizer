"""PMO-22: one chunked content hash, shared by the extractor and sync."""

import hashlib
import io

import pytest
from photo_meta_organizer.domain.hashing import HASH_CHUNK_BYTES, sha256_of_stream


class _RecordingStream(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.read_sizes: list[int] = []

    def read(self, size: int | None = -1) -> bytes:  # type: ignore[override]
        self.read_sizes.append(-1 if size is None else size)
        return super().read(size)


@pytest.mark.unit
class TestSha256OfStream:
    def test_matches_hashlib_across_several_chunks(self) -> None:
        data = bytes(range(256)) * (HASH_CHUNK_BYTES // 256 * 3 + 7)
        assert sha256_of_stream(io.BytesIO(data)) == hashlib.sha256(data).hexdigest()

    def test_empty_stream(self) -> None:
        assert sha256_of_stream(io.BytesIO(b"")) == hashlib.sha256(b"").hexdigest()

    def test_never_reads_the_whole_file_at_once(self) -> None:
        stream = _RecordingStream(b"x" * (HASH_CHUNK_BYTES * 2 + 1))
        sha256_of_stream(stream)
        assert stream.read_sizes, "stream was not read"
        assert all(0 < n <= HASH_CHUNK_BYTES for n in stream.read_sizes)

    def test_hashes_from_the_start_even_after_a_partial_read(self) -> None:
        stream = io.BytesIO(b"hello world")
        stream.read(5)
        assert sha256_of_stream(stream) == hashlib.sha256(b"hello world").hexdigest()
