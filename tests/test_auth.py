import asyncio
import time

import httpx
import pytest

from auth import AuthError, TokenManager
from config import Config


def make_config() -> Config:
    return Config(app_key="test-key", app_secret="test-secret", base_url="https://test.kbsec", timeout_seconds=5)


def token_handler(calls, *, expires_in: int = 86400, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": "bad credentials"})
        return httpx.Response(
            200,
            json={"access_token": f"tok-{len(calls)}", "token_type": "Bearer", "expires_in": expires_in},
        )

    return handler


async def test_get_token_issues_and_caches():
    calls = []
    transport = httpx.MockTransport(token_handler(calls))
    async with httpx.AsyncClient(transport=transport) as client:
        manager = TokenManager(make_config())
        token1 = await manager.get_token(client)
        token2 = await manager.get_token(client)
        assert token1 == token2
        assert len(calls) == 1


async def test_get_token_refreshes_after_expiry():
    calls = []
    transport = httpx.MockTransport(token_handler(calls, expires_in=400))
    async with httpx.AsyncClient(transport=transport) as client:
        manager = TokenManager(make_config())
        token1 = await manager.get_token(client)
        manager._expires_at = time.monotonic() - 1
        token2 = await manager.get_token(client)
        assert token1 != token2
        assert len(calls) == 2


async def test_get_token_raises_auth_error_on_failure():
    calls = []
    transport = httpx.MockTransport(token_handler(calls, status=401))
    async with httpx.AsyncClient(transport=transport) as client:
        manager = TokenManager(make_config())
        with pytest.raises(AuthError):
            await manager.get_token(client)


async def test_invalidate_forces_reissue():
    calls = []
    transport = httpx.MockTransport(token_handler(calls))
    async with httpx.AsyncClient(transport=transport) as client:
        manager = TokenManager(make_config())
        await manager.get_token(client)
        await manager.invalidate()
        await manager.get_token(client)
        assert len(calls) == 2


async def test_concurrent_get_token_issues_once():
    calls = []
    transport = httpx.MockTransport(token_handler(calls))
    async with httpx.AsyncClient(transport=transport) as client:
        manager = TokenManager(make_config())
        results = await asyncio.gather(*[manager.get_token(client) for _ in range(10)])
        assert len(set(results)) == 1
        assert len(calls) == 1
