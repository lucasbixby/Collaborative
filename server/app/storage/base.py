"""Storage interface for large files, addressed by content hash. The rest of the server only
sees hashes, so local disk can be swapped for object storage by adding an implementation."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol


class FileTooLarge(Exception):
    pass


class AssetStore(Protocol):
    async def put_stream(self, chunks: AsyncIterator[bytes], max_bytes: int) -> tuple[str, int]:
        """Store the stream and return (sha256 hex, size). Raises FileTooLarge past `max_bytes`,
        keeping nothing."""
        ...

    def path(self, content_hash: str) -> Path | None:
        """A local path to read the content from, or None if it isn't stored."""
        ...

    async def delete(self, content_hash: str) -> None: ...
