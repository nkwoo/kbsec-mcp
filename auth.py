"""KB증권 OAuth 토큰 발급/캐싱/자동 재발급을 담당한다.

토큰은 프로세스 메모리에만 보관하며 파일/로그에 원문을 남기지 않는다.
실제 HTTP 전송(엔드포인트, envelope, 재시도)은 client.py가 전담하며, 이 모듈은
그 전송 함수를 주입받아 캐싱/락/만료 판단만 책임진다.
"""
import asyncio
import logging
import time
from typing import Awaitable, Callable

from config import Config

logger = logging.getLogger(__name__)

_REFRESH_MARGIN_SECONDS = 300

RequestFn = Callable[[dict], Awaitable[dict]]


class AuthError(RuntimeError):
    """Raised when KB증권 토큰 발급/폐기 요청이 실패했을 때 발생."""


def mask_secret(value: str | None) -> str:
    """로그에 안전하게 남길 수 있도록 시크릿 값을 마스킹한다."""
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


class TokenManager:
    """KB증권 access token을 메모리에 캐싱하고 만료 전 자동으로 재발급한다."""

    def __init__(self, config: Config, request_fn: RequestFn, revoke_fn: RequestFn):
        self._config = config
        self._request_fn = request_fn
        self._revoke_fn = revoke_fn
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        if self._token is not None and time.monotonic() < self._expires_at:
            return self._token
        async with self._lock:
            if self._token is not None and time.monotonic() < self._expires_at:
                return self._token
            await self._issue_token()
        assert self._token is not None
        return self._token

    async def invalidate(self) -> None:
        async with self._lock:
            self._token = None
            self._expires_at = 0.0

    async def revoke(self) -> bool:
        """캐시된 토큰을 KB증권에 폐기 요청하고 로컬 캐시를 비운다.

        KB증권은 토큰 값과 함께 발급 당시의 IP/MAC을 검증하므로, 네트워크 환경이
        바뀌면 만료 전이라도 캐시된 토큰이 전부 검증 실패로 거부될 수 있다. 그런
        경우 원격 폐기 성공 여부와 무관하게 로컬 캐시부터 비워 다음 get_token()
        호출이 현재 IP/MAC 기준으로 즉시 재발급되도록 한다.

        캐시된 토큰이 없으면 원격 호출 없이 False를 반환한다.
        """
        async with self._lock:
            if self._token is None:
                return False
            token = self._token
            self._token = None
            self._expires_at = 0.0
        result = await self._revoke_fn(
            {
                "token": token,
                "appKey": self._config.app_key,
                "appSecret": self._config.app_secret,
            }
        )
        return str(result.get("tokenRevoke", "")).upper() == "Y"

    async def _issue_token(self) -> None:
        # access_token 없이 요청을 보낸다 (get_token -> call -> get_token 무한루프 방지).
        data = await self._request_fn(
            {
                "grantType": "client_credentials",
                "appKey": self._config.app_key,
                "appSecret": self._config.app_secret,
            }
        )
        token = data.get("access_token")
        if not token:
            raise AuthError("Token issuance response missing access_token")
        ttl = float(data.get("expires_in", 86400))
        self._token = token
        self._expires_at = time.monotonic() + max(ttl - _REFRESH_MARGIN_SECONDS, 0)
        logger.debug("Issued new KB증권 access token: %s (ttl=%ss)", mask_secret(token), ttl)
