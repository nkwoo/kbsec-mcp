import asyncio
import json
import re

import httpx
import pytest

from client import KBApiClient, KBApiError, mask_body
from config import Config


async def _no_delay(_seconds: float) -> None:
    return None


def make_config() -> Config:
    return Config(app_key="k", app_secret="s", base_url="https://test.kbsec", timeout_seconds=5)


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


def test_mask_body_redacts_secret_fields():
    body = {"appKey": "abcdefgh1234", "appSecret": "s3cr3t", "shrt_cd": "005930"}
    masked = mask_body(body)
    assert masked["shrt_cd"] == "005930"
    assert masked["appKey"] != "abcdefgh1234"
    assert masked["appSecret"] != "s3cr3t"
