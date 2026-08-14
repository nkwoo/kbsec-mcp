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


def api_response(data_body: dict, *, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        json={"dataHeader": {"rspCd": "00000", "rspMsg": "정상처리"}, "dataBody": data_body},
        headers=headers,
    )


def token_response() -> httpx.Response:
    return api_response({"access_token": "tok-1", "token_type": "Bearer", "expires_in": 86400})


async def test_call_success_returns_data_body():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        assert request.headers["authorization"] == "bearer tok-1"
        return api_response({"is_nm": "삼성전자"})

    client = make_client(handler)
    result = await client.call("/api/v1/ivu10140", {"shrt_cd": "005930"})
    assert result == {"is_nm": "삼성전자"}
    await client.aclose()


async def test_issue_token_wraps_body_in_data_header_and_data_body_envelope():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            sent.update(json.loads(request.content))
            return token_response()
        return api_response({"ok": True})

    client = make_client(handler)
    await client.call("/api/v1/ivu10140", {})
    assert sent["dataBody"] == {
        "grantType": "client_credentials",
        "appKey": "k",
        "appSecret": "s",
    }
    header = sent["dataHeader"]
    assert set(header) == {"ipAddr", "macAddr"}
    assert header["ipAddr"]
    assert re.fullmatch(r"([0-9A-F]{2}-){5}[0-9A-F]{2}", header["macAddr"])
    await client.aclose()


async def test_issue_token_unwraps_data_body_envelope_from_response():
    """KB증권 서버는 다른 모든 API와 동일하게 /oauth2/token 응답도 dataHeader/dataBody로
    감싸서 내려준다. access_token은 dataBody 안에 있으므로 이를 벗겨내야 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return api_response({"access_token": "tok-1", "token_type": "Bearer", "expires_in": 86400})
        assert request.headers["authorization"] == "bearer tok-1"
        return api_response({"ok": True})

    client = make_client(handler)
    result = await client.call("/api/v1/ivu10140", {})
    assert result == {"ok": True}
    await client.aclose()


async def test_issue_token_request_has_no_authorization_header():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            assert "authorization" not in request.headers
            return token_response()
        return api_response({"ok": True})

    client = make_client(handler)
    await client.call("/api/v1/ivu10140", {})
    await client.aclose()


async def test_revoke_token_without_cached_token_is_noop():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/revoke":
            raise AssertionError("should not call /oauth2/revoke without a cached token")
        return api_response({"ok": True})

    client = make_client(handler)
    revoked = await client.revoke_token()
    assert revoked is False
    await client.aclose()


async def test_revoke_token_sends_token_and_credentials_without_auth_header():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        if request.url.path == "/oauth2/revoke":
            assert "authorization" not in request.headers
            sent.update(json.loads(request.content))
            return api_response({"tokenRevoke": "Y"})
        return api_response({"ok": True})

    client = make_client(handler)
    await client.call("/api/v1/ivu10140", {})  # 캐시된 토큰 확보
    revoked = await client.revoke_token()

    assert revoked is True
    assert sent["dataBody"] == {"token": "tok-1", "appKey": "k", "appSecret": "s"}
    await client.aclose()


async def test_revoke_token_forces_reissue_on_next_call():
    state = {"token_calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            state["token_calls"] += 1
            return api_response(
                {"access_token": f"tok-{state['token_calls']}", "token_type": "Bearer", "expires_in": 86400}
            )
        if request.url.path == "/oauth2/revoke":
            return api_response({"tokenRevoke": "Y"})
        assert request.headers["authorization"] == f"bearer tok-{state['token_calls']}"
        return api_response({"ok": True})

    client = make_client(handler)
    await client.call("/api/v1/ivu10140", {})
    await client.revoke_token()
    await client.call("/api/v1/ivu10140", {})

    assert state["token_calls"] == 2
    await client.aclose()


async def test_issue_token_logs_masked_request_body(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        return api_response({"ok": True})

    config = make_config()
    client = make_client(handler, config=Config(
        app_key="my-app-key-1234",
        app_secret="my-app-secret-5678",
        base_url=config.base_url,
        timeout_seconds=config.timeout_seconds,
        trading_enabled=config.trading_enabled,
    ))
    with caplog.at_level("DEBUG", logger="client"):
        await client.call("/api/v1/ivu10140", {})
    await client.aclose()

    token_logged = [r.getMessage() for r in caplog.records if "grantType" in r.getMessage()]
    assert token_logged, "expected token issuance request to be logged"
    message = token_logged[0]
    assert "dataHeader" in message and "dataBody" in message
    assert "my-app-key-1234" not in message
    assert "my-app-secret-5678" not in message


async def test_call_logs_ip_and_mac_address_on_each_request(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        return api_response({"ok": True})

    client = make_client(handler)
    with caplog.at_level("INFO", logger="client"):
        await client.call("/api/v1/ivu10140", {})
    await client.aclose()

    call_logs = [r.getMessage() for r in caplog.records if "KB증권 API call" in r.getMessage()]
    assert call_logs, "expected an API call to be logged"
    for message in call_logs:
        assert re.search(r"ipAddr=\S+", message)
        assert re.search(r"macAddr=([0-9A-F]{2}-){5}[0-9A-F]{2}", message)


async def test_call_wraps_body_in_data_header_and_data_body_envelope():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        sent.update(json.loads(request.content))
        return api_response({"ok": True})

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
            return api_response(
                {"access_token": f"tok-{state['token_calls']}", "token_type": "Bearer", "expires_in": 86400}
            )
        state["api_calls"] += 1
        if state["api_calls"] == 1:
            return httpx.Response(401, json={"msg": "expired"})
        assert request.headers["authorization"] == "bearer tok-2"
        return api_response({"ok": True})

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
        return api_response({"ok": True})

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
        return api_response({"ok": True})

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
        return api_response({"ok": True})

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
        return api_response({"ordr_no": "12345"})

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
        return api_response({"ordr_no": "12345"})

    client = make_client(handler, config=make_config(trading_enabled=True))
    result = await client.call("/api/v1/ssam1801", {}, requires_trading=True)
    assert result == {"ordr_no": "12345"}
    await client.aclose()


async def test_call_without_requires_trading_ignores_trading_flag():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return token_response()
        return api_response({"ok": True})

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
