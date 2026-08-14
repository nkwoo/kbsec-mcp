import asyncio
import time

import pytest

from auth import AuthError, TokenManager
from config import Config


def make_config() -> Config:
    return Config(
        app_key="test-key",
        app_secret="test-secret",
        base_url="https://test.kbsec",
        timeout_seconds=5,
        trading_enabled=False,
    )


def request_fn(calls, *, expires_in: int = 86400, fail: bool = False):
    async def fn(body: dict) -> dict:
        calls.append(body)
        if fail:
            raise AuthError("Token issuance failed with HTTP 401")
        return {"access_token": f"tok-{len(calls)}", "token_type": "Bearer", "expires_in": expires_in}

    return fn


async def test_get_token_issues_and_caches():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls))
    token1 = await manager.get_token()
    token2 = await manager.get_token()
    assert token1 == token2
    assert len(calls) == 1


async def test_get_token_refreshes_after_expiry():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls, expires_in=400))
    token1 = await manager.get_token()
    manager._expires_at = time.monotonic() - 1
    token2 = await manager.get_token()
    assert token1 != token2
    assert len(calls) == 2


async def test_issue_token_sends_grant_type_and_credentials_without_access_token():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls))
    await manager.get_token()
    assert calls[0] == {
        "grantType": "client_credentials",
        "appKey": "test-key",
        "appSecret": "test-secret",
    }
    assert "access_token" not in calls[0]


async def test_get_token_raises_auth_error_on_failure():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls, fail=True))
    with pytest.raises(AuthError):
        await manager.get_token()

async def test_invalidate_forces_reissue():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls))
    await manager.get_token()
    await manager.invalidate()
    await manager.get_token()
    assert len(calls) == 2


async def test_concurrent_get_token_issues_once():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls))
    results = await asyncio.gather(*[manager.get_token() for _ in range(10)])
    assert len(set(results)) == 1
    assert len(calls) == 1
