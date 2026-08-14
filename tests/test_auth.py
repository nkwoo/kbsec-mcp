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


def revoke_fn(calls, *, result: str = "Y", fail: bool = False):
    async def fn(body: dict) -> dict:
        calls.append(body)
        if fail:
            raise AuthError("Token revoke failed with HTTP 401")
        return {"tokenRevoke": result}

    return fn


def _unused_revoke_fn():
    async def fn(body: dict) -> dict:
        raise AssertionError("revoke_fn should not be called in this test")

    return fn


async def test_get_token_issues_and_caches():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls), _unused_revoke_fn())
    token1 = await manager.get_token()
    token2 = await manager.get_token()
    assert token1 == token2
    assert len(calls) == 1


async def test_get_token_refreshes_after_expiry():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls, expires_in=400), _unused_revoke_fn())
    token1 = await manager.get_token()
    manager._expires_at = time.monotonic() - 1
    token2 = await manager.get_token()
    assert token1 != token2
    assert len(calls) == 2


async def test_issue_token_sends_grant_type_and_credentials_without_access_token():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls), _unused_revoke_fn())
    await manager.get_token()
    assert calls[0] == {
        "grantType": "client_credentials",
        "appKey": "test-key",
        "appSecret": "test-secret",
    }
    assert "access_token" not in calls[0]


async def test_get_token_raises_auth_error_on_failure():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls, fail=True), _unused_revoke_fn())
    with pytest.raises(AuthError):
        await manager.get_token()

async def test_invalidate_forces_reissue():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls), _unused_revoke_fn())
    await manager.get_token()
    await manager.invalidate()
    await manager.get_token()
    assert len(calls) == 2


async def test_concurrent_get_token_issues_once():
    calls = []
    manager = TokenManager(make_config(), request_fn(calls), _unused_revoke_fn())
    results = await asyncio.gather(*[manager.get_token() for _ in range(10)])
    assert len(set(results)) == 1
    assert len(calls) == 1


async def test_revoke_without_cached_token_is_noop():
    calls = []
    manager = TokenManager(make_config(), request_fn([]), revoke_fn(calls))
    revoked = await manager.revoke()
    assert revoked is False
    assert calls == []


async def test_revoke_clears_cache_and_sends_token_and_credentials():
    issue_calls = []
    revoke_calls = []
    manager = TokenManager(make_config(), request_fn(issue_calls), revoke_fn(revoke_calls))
    token = await manager.get_token()

    revoked = await manager.revoke()

    assert revoked is True
    assert revoke_calls == [
        {"token": token, "appKey": "test-key", "appSecret": "test-secret"}
    ]
    assert manager._token is None
    assert manager._expires_at == 0.0


async def test_revoke_returns_false_when_kb증권_reports_failure():
    manager = TokenManager(make_config(), request_fn([]), revoke_fn([], result="N"))
    await manager.get_token()
    revoked = await manager.revoke()
    assert revoked is False


async def test_revoke_forces_reissue_on_next_get_token():
    issue_calls = []
    manager = TokenManager(make_config(), request_fn(issue_calls), revoke_fn([]))
    token1 = await manager.get_token()
    await manager.revoke()
    token2 = await manager.get_token()
    assert token1 != token2
    assert len(issue_calls) == 2
