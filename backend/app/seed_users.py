"""Create one demo account per role, in development only.

Run by docker-compose.yml before the backend starts. Idempotent: an email that
already has an account is left untouched. Refuses outside APP_ENV=development,
so these known passwords never reach a shared or production database.
"""

import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.security import hash_password
from app.users import EmailTaken, Role, SqlUserStore

DEMO_PASSWORD = "password123"
DEMO_USERS = {
    "owner@test.com": Role.owner,
    "technician@test.com": Role.technician,
    "admin@test.com": Role.administrator,
}


async def seed() -> None:
    engine = create_async_engine(get_settings().database_url)
    store = SqlUserStore(engine)
    try:
        for email, role in DEMO_USERS.items():
            try:
                await store.create(email, hash_password(DEMO_PASSWORD), role)
                print(f"seed: created {role} {email}")
            except EmailTaken:
                print(f"seed: {email} already exists")
    finally:
        await engine.dispose()


def main() -> int:
    env = get_settings().app_env
    if env != "development":
        print(f"seed: skipped, APP_ENV is {env}")
        return 0
    asyncio.run(seed())
    return 0


if __name__ == "__main__":
    sys.exit(main())
