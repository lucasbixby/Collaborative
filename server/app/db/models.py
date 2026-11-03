"""SQLAlchemy models: users, rooms, room members, operation log, snapshots."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# TODO: User, Room, RoomMember(role), Snapshot


class Base(DeclarativeBase):
    pass


class Operation(Base):
    """One relayed operation (#19).

    `seq` is the server's arrival order and the catch-up cursor, not `lamport`: two operations
    can share a Lamport and a late one can carry an old one, while "everything after this seq"
    is exact. `sqlite_autoincrement` means a seq is never reused, even if the newest rows are
    deleted later, which a plain SQLite rowid doesn't promise (D-068).
    """

    __tablename__ = "operations"
    __table_args__ = (
        Index("ix_operations_room_seq", "room_id", "seq"),
        {"sqlite_autoincrement": True},
    )

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(64))
    lamport: Mapped[int] = mapped_column(BigInteger)
    origin: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(16))
    object: Mapped[str] = mapped_column(String(36))
    payload: Mapped[str] = mapped_column(Text)  # the operation as validated JSON
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
