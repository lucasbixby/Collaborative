"""Storage interface for large assets, addressed by content hash.

The sync engine only ever sees hashes, so local disk can later be swapped for
object storage (e.g. Cloudflare R2) by adding another implementation.
"""

from typing import Protocol


class AssetStore(Protocol):
    async def put(self, data: bytes) -> str:
        """Store bytes and return their content hash."""
        ...

    async def get(self, content_hash: str) -> bytes:
        ...

    async def exists(self, content_hash: str) -> bool:
        ...
