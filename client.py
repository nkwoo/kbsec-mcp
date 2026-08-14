"""KB증권 OpenAPI 공통 HTTP 클라이언트.

모든 API 호출은 이 모듈의 `call()`을 거친다. 토큰 발급/재발급, 재시도, 에러 변환을
한 곳에서 처리해 tools/*.py는 얇게 유지한다.
"""
import asyncio
import json
import logging
import socket
import uuid

import httpx

from auth import AuthError, TokenManager, mask_secret
from config import Config, load_config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_MASKED_BODY_KEYS = {"appkey", "appsecret", "access_token", "token"}
_MAX_RETRY_DELAY_SECONDS = 60


def _detect_local_ip() -> str:
    """외부 통신에 실제로 사용되는 로컬 IP를 추정한다.

    UDP 소켓으로 라우팅 테이블만 조회할 뿐 패킷을 전송하지는 않는다.
    조회에 실패하면(예: 네트워크 미연결) 루프백 주소로 폴백한다.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _detect_mac_address() -> str:
    """로컬 NIC의 MAC 주소를 `XX-XX-XX-XX-XX-XX` 형식으로 반환한다."""
    node = uuid.getnode()
    return "-".join(f"{(node >> shift) & 0xFF:02X}" for shift in range(40, -8, -8))


class KBApiError(RuntimeError):
    """KB증권 API가 에러를 반환했을 때 발생하는 표준화된 예외."""

    def __init__(self, status_code: int, message: str):
        super().__init__(f"KB증권 API error (HTTP {status_code}): {message}")
        self.status_code = status_code
        self.message = message


class TradingDisabledError(RuntimeError):
    """실거래(주문 접수/정정/취소) 도구가 KBSEC_ENABLE_TRADING 비활성화 상태에서 호출되었을 때 발생."""

    def __init__(self, path: str):
        super().__init__(
            f"실거래 도구 호출이 차단되었습니다 ({path}). "
            "활성화하려면 .env에 KBSEC_ENABLE_TRADING=true를 설정하세요."
        )
        self.path = path


def mask_body(body: dict) -> dict:
    """로그 출력용으로 시크릿 필드를 마스킹한 사본을 반환한다."""
    return {
        key: (mask_secret(str(value)) if key.lower() in _MASKED_BODY_KEYS else value)
        for key, value in body.items()
    }


def _extract_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(data, dict):
        for key in ("o_msg", "msg", "message", "error_description"):
            if data.get(key):
                return str(data[key])
    return str(data)


class KBApiClient:
    """토큰 관리와 재시도 정책을 포함한 KB증권 API 클라이언트."""

    def __init__(self, config: Config | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self._config = config or load_config()
        self._http = httpx.AsyncClient(timeout=self._config.timeout_seconds, transport=transport)
        self._ip_addr = _detect_local_ip()
        self._mac_addr = _detect_mac_address()
        self._tokens = TokenManager(self._config, self._issue_token_request, self._revoke_token_request)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def call(self, path: str, body: dict, *, requires_trading: bool = False) -> dict:
        if requires_trading and not self._config.trading_enabled:
            raise TradingDisabledError(path)

        token = await self._tokens.get_token()
        headers = {"Content-Type": "application/json", "Authorization": f"bearer {token}"}
        allow_auth_retry = True

        while True:
            response = await self._post_with_retries(path, body, headers)

            if response.status_code == 401 and allow_auth_retry:
                allow_auth_retry = False
                await self._tokens.invalidate()
                token = await self._tokens.get_token()
                headers["Authorization"] = f"bearer {token}"
                continue

            if response.status_code >= 400:
                raise KBApiError(response.status_code, _extract_error_message(response))

            return response.json()["dataBody"]

    async def _issue_token_request(self, body: dict) -> dict:
        """토큰 발급 요청을 access_token 없이 보낸다.

        TokenManager.get_token()이 이 콜백을 통해서만 KB증권에 요청을 보내므로,
        call()이 토큰을 얻으려고 다시 get_token()을 부르는 무한루프가 생기지 않는다.
        """
        response = await self._post_with_retries("/oauth2/token", body, {"Content-Type": "application/json"})
        if response.status_code != 200:
            raise AuthError(f"Token issuance failed with HTTP {response.status_code}")
        return response.json()["dataBody"]

    async def revoke_token(self) -> bool:
        """캐시된 access token을 폐기하고 다음 호출에서 재발급을 강제한다.

        캐시된 토큰이 없으면 KB증권에 요청을 보내지 않고 False를 반환한다.
        """
        return await self._tokens.revoke()

    async def _revoke_token_request(self, body: dict) -> dict:
        """토큰 폐기 요청을 access_token 없이 보낸다 (KB증권 스펙상 auth: noauth)."""
        response = await self._post_with_retries("/oauth2/revoke", body, {"Content-Type": "application/json"})
        if response.status_code != 200:
            raise AuthError(f"Token revoke failed with HTTP {response.status_code}")
        return response.json()["dataBody"]

    async def _post_with_retries(self, path: str, body: dict, headers: dict) -> httpx.Response:
        """dataHeader/dataBody envelope으로 감싸 POST하고 네트워크 오류/429/5xx는 재시도한다.

        401을 포함한 4xx 응답은 그대로 반환하므로, 인증 재시도 여부는 호출자가 결정한다.
        """
        url = f"{self._config.base_url}{path}"
        envelope = {
            "dataHeader": {"ipAddr": self._ip_addr, "macAddr": self._mac_addr},
            "dataBody": body,
        }
        logged_envelope = {**envelope, "dataBody": mask_body(body)}
        logger.debug("KB증권 API request: POST %s %s", path, json.dumps(logged_envelope, ensure_ascii=False))

        attempt = 0
        while True:
            attempt += 1
            logger.info(
                "KB증권 API call: POST %s (attempt %s, ipAddr=%s, macAddr=%s)",
                path, attempt, self._ip_addr, self._mac_addr,
            )
            try:
                response = await self._http.post(url, json=envelope, headers=headers)
            except httpx.TransportError as exc:
                if attempt >= _MAX_RETRIES:
                    raise KBApiError(0, f"Network error after {attempt} attempts: {exc}") from exc
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            if response.status_code == 429:
                if attempt >= _MAX_RETRIES:
                    raise KBApiError(429, "Rate limited by KB증권 API")
                retry_after = response.headers.get("Retry-After")
                delay = 2 ** (attempt - 1)
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        pass
                delay = min(delay, _MAX_RETRY_DELAY_SECONDS)
                await asyncio.sleep(delay)
                continue

            if response.status_code >= 500:
                if attempt >= _MAX_RETRIES:
                    raise KBApiError(response.status_code, "KB증권 API server error")
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            return response


_client: KBApiClient | None = None


def get_client() -> KBApiClient:
    global _client
    if _client is None:
        _client = KBApiClient()
    return _client


async def call(path: str, body: dict, *, requires_trading: bool = False) -> dict:
    return await get_client().call(path, body, requires_trading=requires_trading)


async def revoke_token() -> bool:
    return await get_client().revoke_token()
