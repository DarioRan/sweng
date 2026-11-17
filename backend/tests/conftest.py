"""Shared fixtures: an in-memory user store and signed-in clients, so no store is needed."""

import asyncio
import os
from collections.abc import Callable, Iterator

# A 32+ byte key, set before the app reads its settings.
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.security import get_user_store, hash_password, issue_token  # noqa: E402
from app.users import InMemoryUserStore, Role  # noqa: E402

PASSWORD = "correct horse battery"


@pytest.fixture
def users() -> Iterator[InMemoryUserStore]:
    store = InMemoryUserStore()
    app.dependency_overrides[get_user_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_user_store, None)


@pytest.fixture
def client(users: InMemoryUserStore) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_header(users: InMemoryUserStore) -> Callable[[Role], dict[str, str]]:
    """Create a user with the given role and return a bearer header for them."""

    def make(role: Role) -> dict[str, str]:
        email = f"{role.value}-{len(users._by_id)}@example.com"
        user = asyncio.run(users.create(email, hash_password(PASSWORD), role))
        return {"Authorization": f"Bearer {issue_token(user, get_settings())}"}

    return make
