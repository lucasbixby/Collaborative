"""REST: a room's project file, the host's .blend.

The host uploads it when creating the room and again whenever they save; every member's app
downloads it before launching Blender, so everyone starts from the same file. Content lives in
the asset store by hash; the room row records which hash is current.
"""

import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from app.api.rooms import FileOut, _delete_file_if_unused, _require_owner, file_of
from app.auth.dependencies import Session
from app.auth.membership import Member
from app.config import settings
from app.storage.base import FileTooLarge

router = APIRouter()

# How a .blend starts: plain, zstd-compressed (Blender 3.0+) or gzip-compressed (older).
_BLEND_MAGIC = (b"BLENDER", b"\x28\xb5\x2f\xfd", b"\x1f\x8b")
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9 ._()\-]")


def _display_name(name: str) -> str:
    """The upload's file name, reduced to a plain `.blend` name that is safe to show and to use
    as a file name on another computer. No path parts survive."""
    base = re.split(r"[\\/]", name)[-1]
    base = _UNSAFE_NAME.sub("_", base).strip(" .")[:120] or "project"
    return base if base.lower().endswith(".blend") else f"{base}.blend"


async def _checked(chunks):
    """Pass the upload through, refusing it unless it starts like a .blend file."""
    head = b""
    async for chunk in chunks:
        if len(head) < 8:
            head += chunk[: 8 - len(head)]
            if len(head) >= 7 and not head.startswith(_BLEND_MAGIC):
                raise ValueError("not a .blend file")
        yield chunk
    if not head.startswith(_BLEND_MAGIC):
        raise ValueError("not a .blend file")


@router.put("/{room_id}/file")
async def upload_file(
    request: Request,
    member: Member,
    session: Session,
    name: Annotated[str, Query(max_length=255)] = "project.blend",
) -> FileOut:
    """Replace the room's project file with the request body (the raw bytes, streamed to disk)."""
    _require_owner(member)
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > settings.max_file_bytes:
        raise HTTPException(413, "that file is too large")
    assets = request.app.state.assets
    try:
        file_hash, size = await assets.put_stream(
            _checked(request.stream()), settings.max_file_bytes
        )
    except FileTooLarge:
        raise HTTPException(413, "that file is too large") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    room = member.room
    previous = room.file_hash
    room.file_hash, room.file_size = file_hash, size
    room.file_name = _display_name(name)
    room.file_updated_at = datetime.now(UTC)
    session.add(room)
    await session.commit()
    if previous is not None and previous != file_hash:
        await _delete_file_if_unused(session, assets, previous)
    return file_of(room)


@router.get("/{room_id}/file")
async def download_file(request: Request, member: Member) -> FileResponse:
    room = member.room
    path = request.app.state.assets.path(room.file_hash) if room.file_hash else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this room has no project file yet")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=room.file_name,
        headers={"ETag": f'"{room.file_hash}"'},
    )
