"""The demo accounts have known passwords: the seed must never run outside development."""

import pytest

from app import seed_users
from app.config import Settings
from app.users import Role


def test_one_demo_account_per_role() -> None:
    assert sorted(seed_users.DEMO_USERS.values()) == sorted(Role)


@pytest.mark.parametrize("env", ["test", "production"])
def test_seed_refuses_outside_development(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    settings = Settings(app_env=env, secret_key="s" * 48)
    monkeypatch.setattr(seed_users, "get_settings", lambda: settings)

    async def must_not_run() -> None:
        raise AssertionError("seeded outside development")

    monkeypatch.setattr(seed_users, "seed", must_not_run)
    assert seed_users.main() == 0
