"""Content hashing: the one definition of a photo's identity (``file_hash``).

Pure over a stream: the caller opens the file (through a retriever), this module only
reads it, in fixed-size chunks, so memory stays flat however large the photo is.
Used by the extractor when indexing and by sync when it must confirm a change.
"""

import hashlib
from typing import BinaryIO

HASH_CHUNK_BYTES = 1024 * 1024


def sha256_of_stream(stream: BinaryIO) -> str:
    """SHA-256 hex digest of the whole stream, read from the start in chunks."""
    stream.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(HASH_CHUNK_BYTES), b""):
        digest.update(chunk)
    return digest.hexdigest()
