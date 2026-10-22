"""T-402: sign-in issues a signed token, three roles, every endpoint checks the role server-side."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import app
from app.security import hash_password, verify_password
from app.users import InMemoryUserStore, Role
from tests.conftest import PASSWORD

AuthHeader = Callable[[Role], dict[str, str]]

PUBLIC = {"/api/auth/login", "/api/auth/register"}
ASK = {"question": "torque?", "job_id": "j1"}
DOCUMENT = {
    "files": {"pdf": ("m.pdf", b"%PDF-1.4", "application/pdf")},
    "data": {"source": "s", "licence_basis": "l", "retrieval_date": "2026-01-01"},
}


def test_three_roles_exist() -> None:
    assert {r.value for r in Role} == {"owner", "technician", "administrator"}


# ------------------------------------------------------------- passwords


def test_passwords_are_hashed_with_argon2id() -> None:
    hashed = hash_password(PASSWORD)
    assert hashed.startswith("$argon2id$")
    assert PASSWORD not in hashed
    assert verify_password(hashed, PASSWORD)
    assert not verify_password(hashed, PASSWORD + "x")


def test_registration_stores_only_the_hash(client: TestClient, users: InMemoryUserStore) -> None:
    client.post("/api/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    (user,) = users._by_id.values()
    assert user.password_hash.startswith("$argon2id$")


# ------------------------------------------------------------- sign-in


def test_sign_in_issues_a_signed_token(client: TestClient, users: InMemoryUserStore) -> None:
    client.post("/api/auth/register", json={"email": "Ann@Example.com", "password": PASSWORD})

    response = client.post(
        "/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    token = response.json()["access_token"]
    claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    (user,) = users._by_id.values()
    assert claims["sub"] == user.id
    assert claims["role"] == "owner"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json() == {"id": user.id, "email": "ann@example.com", "role": "owner"}


@pytest.mark.parametrize(
    "email,password", [("a@example.com", "wrong-password"), ("nobody@example.com", PASSWORD)]
)
def test_sign_in_rejects_bad_credentials(client: TestClient, email: str, password: str) -> None:
    client.post("/api/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_self_registration_cannot_pick_a_role(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": PASSWORD, "role": "administrator"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "owner"


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    body = {"email": "a@example.com", "password": PASSWORD}
    client.post("/api/auth/register", json=body)
    again = client.post("/api/auth/register", json={**body, "email": "A@example.com"})
    assert again.status_code == 409


# ------------------------------------------------------------- tokens


def _forge(claims: dict, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt.encode(claims, key, algorithm='HS256')}"}


def test_token_signed_with_another_key_is_rejected(
    client: TestClient, users: InMemoryUserStore, auth_header: AuthHeader
) -> None:
    auth_header(Role.owner)
    (user,) = users._by_id.values()
    exp = datetime.now(UTC) + timedelta(minutes=5)
    forged = _forge({"sub": user.id, "role": "administrator", "exp": exp}, "x" * 48)
    assert client.get("/api/auth/me", headers=forged).status_code == 401


def test_expired_token_is_rejected(
    client: TestClient, users: InMemoryUserStore, auth_header: AuthHeader
) -> None:
    auth_header(Role.owner)
    (user,) = users._by_id.values()
    exp = datetime.now(UTC) - timedelta(seconds=1)
    expired = _forge({"sub": user.id, "exp": exp}, get_settings().secret_key)
    assert client.get("/api/auth/me", headers=expired).status_code == 401


def test_role_claim_in_token_is_not_trusted(
    client: TestClient, users: InMemoryUserStore, auth_header: AuthHeader
) -> None:
    """A validly signed token claiming a higher role still gets the stored role."""
    auth_header(Role.owner)
    (user,) = users._by_id.values()
    exp = datetime.now(UTC) + timedelta(minutes=5)
    lying = _forge({"sub": user.id, "role": "administrator", "exp": exp}, get_settings().secret_key)
    assert client.post("/api/documents", headers=lying, **DOCUMENT).status_code == 403


# ------------------------------------------------------------- role enforcement


def test_every_api_endpoint_requires_sign_in(client: TestClient) -> None:
    """Guards future endpoints too: anything under /api not listed in PUBLIC must reject."""
    paths = client.get("/openapi.json").json()["paths"]
    routes = [
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith("/api") and path not in PUBLIC
        for method in operations
    ]
    assert len(routes) >= 7  # the five contracts, /auth/me, /admin/users
    for method, path in routes:
        response = client.request(method, path)
        assert response.status_code == 401, (method, path)


@pytest.mark.parametrize(
    "role,method,path,kwargs",
    [
        (Role.owner, "POST", "/api/documents", DOCUMENT),
        (Role.technician, "POST", "/api/documents", DOCUMENT),
        (Role.administrator, "POST", "/api/ask", {"json": ASK}),
        (Role.administrator, "GET", "/api/figure?component=chain", {}),
        (
            Role.owner,
            "POST",
            "/api/admin/users",
            {"json": {"email": "t@example.com", "password": PASSWORD, "role": "technician"}},
        ),
        (
            Role.technician,
            "POST",
            "/api/admin/users",
            {"json": {"email": "t@example.com", "password": PASSWORD, "role": "administrator"}},
        ),
    ],
)
def test_wrong_role_is_rejected(
    client: TestClient, auth_header: AuthHeader, role: Role, method: str, path: str, kwargs: dict
) -> None:
    response = client.request(method, path, headers=auth_header(role), **kwargs)
    assert response.status_code == 403


@pytest.mark.parametrize(
    "role,method,path,kwargs",
    [
        (Role.owner, "POST", "/api/ask", {"json": ASK}),
        (Role.technician, "POST", "/api/ask", {"json": ASK}),
        (Role.technician, "GET", "/api/figure?component=chain", {}),
        (Role.administrator, "POST", "/api/documents", DOCUMENT),
    ],
)
def test_right_role_reaches_the_endpoint(
    client: TestClient, auth_header: AuthHeader, role: Role, method: str, path: str, kwargs: dict
) -> None:
    response = client.request(method, path, headers=auth_header(role), **kwargs)
    assert response.status_code == 501  # past the role check, into the stub


def test_administrator_creates_a_technician(client: TestClient, auth_header: AuthHeader) -> None:
    response = client.post(
        "/api/admin/users",
        headers=auth_header(Role.administrator),
        json={"email": "tech@example.com", "password": PASSWORD, "role": "technician"},
    )
    assert response.status_code == 201
    login = client.post("/api/auth/login", json={"email": "tech@example.com", "password": PASSWORD})
    assert login.json()["role"] == "technician"


# ------------------------------------------------------------- development bypass


@pytest.fixture
def auth_disabled() -> Iterator[None]:
    settings = get_settings().model_copy(update={"auth_disabled": True})
    app.dependency_overrides[get_settings] = lambda: settings
    yield
    app.dependency_overrides.pop(get_settings, None)


def test_bypass_is_off_by_default() -> None:
    assert Settings().auth_disabled is False


@pytest.mark.parametrize("env", ["test", "production"])
def test_bypass_refused_outside_development(env: str) -> None:
    with pytest.raises(ValidationError, match="AUTH_DISABLED"):
        Settings(app_env=env, auth_disabled=True, secret_key="s" * 48)


def test_bypass_lets_tokenless_requests_through_every_role(
    client: TestClient, auth_disabled: None
) -> None:
    assert client.post("/api/ask", json=ASK).status_code == 501
    assert client.post("/api/documents", **DOCUMENT).status_code == 501


def test_bypass_still_checks_requests_with_a_token(
    client: TestClient, auth_header: AuthHeader, auth_disabled: None
) -> None:
    owner = auth_header(Role.owner)
    assert client.post("/api/documents", headers=owner, **DOCUMENT).status_code == 403
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.post("/api/ask", headers=bad, json=ASK).status_code == 401
