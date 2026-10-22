"""Password hashing, signed tokens and the server-side role check (T-402).

Passwords: Argon2id, memory-hard (argon2-cffi defaults, RFC 9106 low-memory profile).
Tokens:    HS256 JWT signed with SECRET_KEY; `sub` is the user id.
Roles:     every protected route declares `Depends(require_roles(...))`. The role is
           read from the user record on each request, not trusted from the token,
           so a role change or a deleted account takes effect immediately.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.users import Role, User, UserStore

_ALGORITHM = "HS256"
_hasher = PasswordHasher()
# Verified against when the email is unknown, so a miss costs as much as a hit.
_DUMMY_HASH = _hasher.hash("timing-equaliser")


# ------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


async def authenticate(store: UserStore, email: str, password: str) -> User | None:
    user = await store.get_by_email(email)
    if user is None:
        verify_password(_DUMMY_HASH, password)
        return None
    return user if verify_password(user.password_hash, password) else None


# ------------------------------------------------------------- tokens


def issue_token(user: User, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user.id,
        "role": user.role.value,  # informational, for the client; the server re-reads it
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str, settings: Settings) -> str | None:
    """The user id the token was issued to, or None if it is forged, malformed or expired."""
    try:
        claims = jwt.decode(
            token, settings.secret_key, algorithms=[_ALGORITHM], options={"require": ["sub", "exp"]}
        )
    except jwt.PyJWTError:
        return None
    return claims["sub"]


# ------------------------------------------------------------- dependencies


def get_user_store(request: Request) -> UserStore:
    return request.app.state.users


_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not signed in.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    store: Annotated[UserStore, Depends(get_user_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None:
        raise _UNAUTHENTICATED
    user_id = decode_token(credentials.credentials, settings)
    user = await store.get_by_id(user_id) if user_id else None
    if user is None:
        raise _UNAUTHENTICATED
    return user


def require_roles(*roles: Role) -> Callable[..., Awaitable[User]]:
    """401 when not signed in, 403 when signed in with a role outside `roles`."""
    allowed = frozenset(roles)

    async def check(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(sorted(allowed))}.",
            )
        return user

    return check
