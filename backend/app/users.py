"""Accounts and roles (FR-01, T-402).

Three roles, nothing else. The store is an interface so the auth tests run
without PostgreSQL; the dev stack uses the SQL implementation.
"""

import asyncio
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    Row,
    Select,
    String,
    Table,
    func,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine


class Role(StrEnum):
    owner = "owner"
    technician = "technician"
    administrator = "administrator"


@dataclass(frozen=True)
class User:
    id: str
    email: str
    password_hash: str
    role: Role


class EmailTaken(Exception):
    pass


def normalise_email(email: str) -> str:
    return email.strip().lower()


class UserStore(Protocol):
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: str) -> User | None: ...
    async def create(self, email: str, password_hash: str, role: Role) -> User: ...


# ------------------------------------------------------------- PostgreSQL

metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("email", CITEXT, nullable=False, unique=True),  # citext: 000_extensions.sql
    Column("password_hash", String, nullable=False),
    Column("role", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class SqlUserStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def _ensure_schema(self) -> None:
        # Stand-in until the backend has migrations: create the table on first use,
        # so the app still starts (and /health still reports) with the database down.
        if self._schema_ready:
            return
        async with self._schema_lock:
            if not self._schema_ready:
                async with self._engine.begin() as conn:
                    await conn.run_sync(metadata.create_all)
                self._schema_ready = True

    @staticmethod
    def _to_user(row: Row) -> User:
        return User(
            id=str(row.id), email=row.email, password_hash=row.password_hash, role=Role(row.role)
        )

    async def _one(self, statement: Select) -> User | None:
        await self._ensure_schema()
        async with self._engine.connect() as conn:
            row = (await conn.execute(statement)).first()
        return self._to_user(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        return await self._one(
            select(users_table).where(users_table.c.email == normalise_email(email))
        )

    async def get_by_id(self, user_id: str) -> User | None:
        try:
            uuid.UUID(user_id)
        except ValueError:
            return None
        return await self._one(select(users_table).where(users_table.c.id == user_id))

    async def create(self, email: str, password_hash: str, role: Role) -> User:
        await self._ensure_schema()
        user = User(str(uuid.uuid4()), normalise_email(email), password_hash, role)
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    insert(users_table).values(
                        id=user.id,
                        email=user.email,
                        password_hash=user.password_hash,
                        role=user.role.value,
                    )
                )
        except IntegrityError as exc:
            raise EmailTaken(user.email) from exc
        return user


# ------------------------------------------------------------- in memory


class InMemoryUserStore:
    """For tests."""

    def __init__(self) -> None:
        self._by_id: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        email = normalise_email(email)
        return next((u for u in self._by_id.values() if u.email == email), None)

    async def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    async def create(self, email: str, password_hash: str, role: Role) -> User:
        if await self.get_by_email(email):
            raise EmailTaken(normalise_email(email))
        user = User(str(uuid.uuid4()), normalise_email(email), password_hash, role)
        self._by_id[user.id] = user
        return user
