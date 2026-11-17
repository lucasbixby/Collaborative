"""SQLAlchemy models: users, rooms and their members, the operation log, snapshots."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """A timestamp that reads back in UTC. SQLite keeps no time zone, so without this a stored
    UTC time comes back naive and can't be compared with `datetime.now(UTC)`."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # scrypt, see app.auth.passwords
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Room(Base):
    """A room. Its id is the name people type to join it. `created_by` is the host shown in the
    UI; who may do what is decided by RoomMember roles. The file columns describe the room's
    project file (the host's .blend) in the asset store, or are all None before an upload."""

    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # None for a room made by scripts/admin.py without one: joinable only through add-member.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class RoomMember(Base):
    """One user's role in one room: "owner", "editor" or "viewer" (app.auth.permissions)."""

    __tablename__ = "room_members"

    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(16))
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime)


class OriginOwner(Base):
    """Which user an `origin` belongs to: the first user to send as it. In the database so a
    restart doesn't let someone else claim it."""

    __tablename__ = "origin_owners"

    origin: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    claimed_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Operation(Base):
    """One relayed operation. `seq` is the server's arrival order and the catch-up cursor.
    AUTOINCREMENT means a seq is never reused, which a plain SQLite rowid doesn't promise."""

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
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Snapshot(Base):
    """A room's folded state up to and including `seq`: a cache over the log, so any snapshot
    can be rebuilt from it. `state` is `RoomState.to_json()`."""

    __tablename__ = "snapshots"
    __table_args__ = (Index("ix_snapshots_room_seq", "room_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
