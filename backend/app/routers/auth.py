"""Sign-in and account endpoints (FR-01, T-402).

Self sign-up always creates an owner. Technician and administrator accounts are
created by an administrator, or from the command line for the first one
(`python -m app.create_user`).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.security import authenticate, get_user_store, hash_password, issue_token, require_roles
from app.users import EmailTaken, Role, User, UserStore

router = APIRouter(prefix="/api", tags=["auth"])

ANY_ROLE = tuple(Role)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    # Upper bound keeps one request from making Argon2 hash megabytes.
    password: str = Field(min_length=8, max_length=128)


class NewUser(Credentials):
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class UserResponse(BaseModel):
    id: str
    email: str
    role: Role

    @classmethod
    def of(cls, user: User) -> "UserResponse":
        return cls(id=user.id, email=user.email, role=user.role)


async def _create(store: UserStore, body: Credentials, role: Role) -> User:
    try:
        return await store.create(body.email, hash_password(body.password), role)
    except EmailTaken:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That email already has an account."
        ) from None


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: Credentials,
    store: Annotated[UserStore, Depends(get_user_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    user = await authenticate(store, body.email, body.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Wrong email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=issue_token(user, settings), role=user.role)


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: Credentials,
    store: Annotated[UserStore, Depends(get_user_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    user = await _create(store, body, Role.owner)
    return TokenResponse(access_token=issue_token(user, settings), role=user.role)


@router.get("/auth/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(require_roles(*ANY_ROLE))]) -> UserResponse:
    return UserResponse.of(user)


@router.post(
    "/admin/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(Role.administrator))],
)
async def create_user(
    body: NewUser, store: Annotated[UserStore, Depends(get_user_store)]
) -> UserResponse:
    return UserResponse.of(await _create(store, body, body.role))
