import asyncio
import json
import re

import httpx
import pytest

from client import KBApiClient, KBApiError, TradingDisabledError, mask_body
from config import Config


async def _no_delay(_seconds: float) -> None:
    return None


def make_config(*, trading_enabled: bool = False) -> Config:
    return Config(
        app_key="k",
        app_secret="s",
        base_url="https://test.kbsec",
        timeout_seconds=5,
        trading_enabled=trading_enabled,
    )


def make_client(handler, config=None) -> KBApiClient:
    transport = httpx.MockTransport(handler)
    return KBApiClient(config=config or make_config(), transport=transport)


def token_response() -> httpx.Response:
    return httpx.Response(200, json={"access_token": "tok-1", "token_type": "Bearer", "expires_in": 86400})


async def test_call_success_returns_json():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        assert request.headers["authorization"] == "bearer tok-1"
        return httpx.Response(200, json={"is_nm": "삼성전자"})

    client = make_client(handler)
    result = await client.call("/api/v1/ivu10140", {"shrt_cd": "005930"})
    assert result == {"is_nm": "삼성전자"}
    await client.aclose()


async def test_call_wraps_body_in_data_header_and_data_body_envelope():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    await client.call("/api/v1/ivu10210", {"excg_clsf": "0", "mkt_clsf": "1"})
    assert sent["dataBody"] == {"excg_clsf": "0", "mkt_clsf": "1"}
    header = sent["dataHeader"]
    assert set(header) == {"ipAddr", "macAddr"}
    assert header["ipAddr"]
    assert re.fullmatch(r"([0-9A-F]{2}-){5}[0-9A-F]{2}", header["macAddr"])
    await client.aclose()


async def test_call_retries_with_new_token_on_401():
    state = {"token_calls": 0, "api_calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            state["token_calls"] += 1
            return httpx.Response(
                200,
                json={"access_token": f"tok-{state['token_calls']}", "token_type": "Bearer", "expires_in": 86400},
            )
        state["api_calls"] += 1
        if state["api_calls"] == 1:
            return httpx.Response(401, json={"msg": "expired"})
        assert request.headers["authorization"] == "bearer tok-2"
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    result = await client.call("/api/v1/ssqm1801", {})
    assert result == {"ok": True}
    assert state["token_calls"] == 2
    await client.aclose()


async def test_call_raises_kb_api_error_on_4xx_with_message():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        return httpx.Response(400, json={"o_msg": "주문수량 오류"})

    client = make_client(handler)
    with pytest.raises(KBApiError) as exc_info:
        await client.call("/api/v1/ssam1801", {})
    assert "주문수량 오류" in str(exc_info.value)
    assert exc_info.value.status_code == 400
    await client.aclose()


async def test_call_retries_5xx_then_raises(monkeypatch):
    monkeypatch.setattr("client.asyncio.sleep", _no_delay)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        attempts["count"] += 1
        return httpx.Response(500, json={"msg": "server error"})

    client = make_client(handler)
    with pytest.raises(KBApiError):
        await client.call("/api/v1/ivu10140", {})
    assert attempts["count"] == 3
    await client.aclose()


async def test_call_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("client.asyncio.sleep", _no_delay)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    result = await client.call("/api/v1/ivu10140", {})
    assert result == {"ok": True}
    assert attempts["count"] == 2
    await client.aclose()


async def test_call_429_with_non_numeric_retry_after_falls_back_to_backoff(monkeypatch):
    sleeps = []

    async def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("client.asyncio.sleep", _record_sleep)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    result = await client.call("/api/v1/ivu10140", {})
    assert result == {"ok": True}
    assert attempts["count"] == 2
    # Non-numeric Retry-After must not crash; falls back to exponential backoff (2 ** (1-1) == 1).
    assert sleeps == [1]
    await client.aclose()


async def test_call_429_with_large_retry_after_is_clamped(monkeypatch):
    sleeps = []

    async def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("client.asyncio.sleep", _record_sleep)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(429, headers={"Retry-After": "3600"})
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    result = await client.call("/api/v1/ivu10140", {})
    assert result == {"ok": True}
    assert attempts["count"] == 2
    assert sleeps == [60]
    await client.aclose()


async def test_call_blocks_trading_when_disabled():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if request.url.path == "/oauth2/token":
            return token_response()
        return httpx.Response(200, json={"ordr_no": "12345"})

    client = make_client(handler, config=make_config(trading_enabled=False))
    with pytest.raises(TradingDisabledError):
        await client.call("/api/v1/ssam1801", {}, requires_trading=True)
    # No HTTP call (not even token issuance) should happen for a blocked trade call.
    assert calls["count"] == 0
    await client.aclose()


async def test_call_allows_trading_when_enabled():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        return httpx.Response(200, json={"ordr_no": "12345"})

    client = make_client(handler, config=make_config(trading_enabled=True))
    result = await client.call("/api/v1/ssam1801", {}, requires_trading=True)
    assert result == {"ordr_no": "12345"}
    await client.aclose()


async def test_call_without_requires_trading_ignores_trading_flag():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler, config=make_config(trading_enabled=False))
    result = await client.call("/api/v1/ivu10140", {})
    assert result == {"ok": True}
    await client.aclose()


def test_mask_body_redacts_secret_fields():
    body = {"appKey": "abcdefgh1234", "appSecret": "s3cr3t", "shrt_cd": "005930"}
    masked = mask_body(body)
    assert masked["shrt_cd"] == "005930"
    assert masked["appKey"] != "abcdefgh1234"
    assert masked["appSecret"] != "s3cr3t"
