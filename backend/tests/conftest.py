"""Shared fixtures: an in-memory user store and signed-in clients, so no store is needed."""

import asyncio
import os
from collections.abc import Callable, Iterator

# A 32+ byte key, set before the app reads its settings.
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.corpus.indexer import get_indexer  # noqa: E402
from app.corpus.ingest import Outcome  # noqa: E402
from app.documents import InMemoryDocumentStore  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.api import get_document_store  # noqa: E402
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
def documents() -> Iterator[InMemoryDocumentStore]:
    store = InMemoryDocumentStore()
    app.dependency_overrides[get_document_store] = lambda: store
    yield store
    app.dependency_overrides.pop(get_document_store, None)


class FakeIndexer:
    """Stands in for app.corpus.indexer.CorpusIndexer: no Qdrant, S3 or embedder touched."""

    def __init__(self, pages: int = 3, ok: bool = True) -> None:
        self.pages = pages
        self.ok = ok
        self.calls: list[dict] = []

    async def index(self, row: dict[str, str], pdf_bytes: bytes, filename: str) -> Outcome:
        self.calls.append({"row": row, "filename": filename, "size": len(pdf_bytes)})
        return Outcome(
            manual=f"{row.get('doc_code')}-{row.get('revision')}",
            status="ok" if self.ok else "NO TEXT: stub indexer",
            pages=self.pages,
            chunks=self.pages,
            indexed=self.pages,
        )


@pytest.fixture
def indexer() -> Iterator[FakeIndexer]:
    fake = FakeIndexer()
    app.dependency_overrides[get_indexer] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_indexer, None)


@pytest.fixture
def client(
    users: InMemoryUserStore, documents: InMemoryDocumentStore, indexer: FakeIndexer
) -> Iterator[TestClient]:
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
