"""AssetStore on local disk: files live at <root>/<hash[:2]>/<hash>."""

import asyncio
import hashlib
import os
import re
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from .base import FileTooLarge

_HASH = re.compile(r"^[0-9a-f]{64}$")


class LocalAssetStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _target(self, content_hash: str) -> Path:
        # Hashes come from the database, but a path is still only ever built from a real one.
        if not _HASH.match(content_hash):
            raise ValueError("not a sha256 hash")
        return self._root / content_hash[:2] / content_hash

    async def put_stream(self, chunks: AsyncIterator[bytes], max_bytes: int) -> tuple[str, int]:
        self._root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        # Written beside its final place, then renamed: a reader never sees half a file.
        fd, temp_name = tempfile.mkstemp(dir=self._root, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as file:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise FileTooLarge
                    digest.update(chunk)
                    await asyncio.to_thread(file.write, chunk)
            content_hash = digest.hexdigest()
            target = self._target(content_hash)
            target.parent.mkdir(exist_ok=True)
            os.replace(temp_name, target)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
        return content_hash, size

    def path(self, content_hash: str) -> Path | None:
        target = self._target(content_hash)
        return target if target.is_file() else None

    async def delete(self, content_hash: str) -> None:
        self._target(content_hash).unlink(missing_ok=True)
