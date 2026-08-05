"""KB증권 OpenAPI 공통 HTTP 클라이언트.

모든 API 호출은 이 모듈의 `call()`을 거친다. 토큰 발급/재발급, 재시도, 에러 변환을
한 곳에서 처리해 tools/*.py는 얇게 유지한다.
"""
import asyncio
import logging
import socket
import uuid

import httpx

from auth import TokenManager, mask_secret
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
        self._tokens = TokenManager(self._config)
        self._ip_addr = _detect_local_ip()
        self._mac_addr = _detect_mac_address()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def call(self, path: str, body: dict) -> dict:
        url = f"{self._config.base_url}{path}"
        token = await self._tokens.get_token(self._http)
        headers = {"Content-Type": "application/json", "Authorization": f"bearer {token}"}
        envelope = {
            "dataHeader": {"ipAddr": self._ip_addr, "macAddr": self._mac_addr},
            "dataBody": body,
        }
        allow_auth_retry = True

        attempt = 0
        while True:
            attempt += 1
            logger.info("KB증권 API call: POST %s (attempt %s)", path, attempt)
            try:
                response = await self._http.post(url, json=envelope, headers=headers)
            except httpx.TransportError as exc:
                if attempt >= _MAX_RETRIES:
                    raise KBApiError(0, f"Network error after {attempt} attempts: {exc}") from exc
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            if response.status_code == 401 and allow_auth_retry:
                allow_auth_retry = False
                await self._tokens.invalidate()
                new_token = await self._tokens.get_token(self._http)
                headers["Authorization"] = f"bearer {new_token}"
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

            if response.status_code >= 400:
                raise KBApiError(response.status_code, _extract_error_message(response))

            return response.json()


_client: KBApiClient | None = None


def get_client() -> KBApiClient:
    global _client
    if _client is None:
        _client = KBApiClient()
    return _client


async def call(path: str, body: dict) -> dict:
    return await get_client().call(path, body)
