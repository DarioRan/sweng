"""Create an account from the command line — how the first administrator gets in.

Usage: docker compose exec backend python -m app.create_user admin@example.com administrator
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.security import hash_password
from app.users import EmailTaken, Role, SqlUserStore


async def _create(email: str, password: str, role: Role) -> None:
    engine = create_async_engine(get_settings().database_url)
    try:
        user = await SqlUserStore(engine).create(email, hash_password(password), role)
    finally:
        await engine.dispose()
    print(f"created {user.role} {user.email} ({user.id})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email")
    parser.add_argument("role", choices=[r.value for r in Role])
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    if len(password) < 8:
        print("password must be at least 8 characters", file=sys.stderr)
        return 1
    if password != getpass.getpass("Repeat: "):
        print("passwords differ", file=sys.stderr)
        return 1
    try:
        asyncio.run(_create(args.email, password, Role(args.role)))
    except EmailTaken:
        print(f"an account for {args.email} already exists", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
