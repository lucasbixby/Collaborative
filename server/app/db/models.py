"""SQLAlchemy models: users, rooms, room members, operation log, snapshots."""

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """A timestamp that reads back in UTC. SQLite keeps no time zone, so without this a time
    written as UTC comes back naive, and comparing it with `datetime.now(UTC)` (an invite's
    expiry) raises."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class User(Base):
    """An account (#16). `password_hash` is scrypt's output with its salt and parameters
    (app.auth.passwords), never the password."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Room(Base):
    """A room (#18). Its id is the human-readable name clients join by, the same pattern the
    socket's URL takes. Who may do what is in RoomMember; `created_by` is only a record."""

    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class RoomMember(Base):
    """One user's role in one room: "owner", "editor" or "viewer" (app.auth.permissions)."""

    __tablename__ = "room_members"

    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(16))
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Invite(Base):
    """An invite code for a room (#18). Only the code's SHA-256 is stored: the code is shown
    once, to the owner who made it, so the database alone can't be used to join. A code can be
    used by any number of people until it expires or is revoked."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


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


class Snapshot(Base):
    """A room's folded state up to and including `seq` (#20): a cache over the log, which is
    never trimmed, so any snapshot can be rebuilt from it. `state` is `RoomState.to_json()`."""

    __tablename__ = "snapshots"
    __table_args__ = (Index("ix_snapshots_room_seq", "room_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
