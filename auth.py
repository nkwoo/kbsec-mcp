"""KB증권 OAuth 토큰 발급/캐싱/자동 재발급을 담당한다.

토큰은 프로세스 메모리에만 보관하며 파일/로그에 원문을 남기지 않는다.
"""
import asyncio
import logging
import time

import httpx

from config import Config

logger = logging.getLogger(__name__)

_REFRESH_MARGIN_SECONDS = 300


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

    def __init__(self, config: Config):
        self._config = config
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self, client: httpx.AsyncClient) -> str:
        if self._token is not None and time.monotonic() < self._expires_at:
            return self._token
        async with self._lock:
            if self._token is not None and time.monotonic() < self._expires_at:
                return self._token
            await self._issue_token(client)
        assert self._token is not None
        return self._token

    async def invalidate(self) -> None:
        async with self._lock:
            self._token = None
            self._expires_at = 0.0

    async def _issue_token(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            f"{self._config.base_url}/oauth2/token",
            json={
                "grantType": "client_credentials",
                "appKey": self._config.app_key,
                "appSecret": self._config.app_secret,
            },
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 200:
            raise AuthError(f"Token issuance failed with HTTP {response.status_code}")
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise AuthError("Token issuance response missing access_token")
        ttl = float(data.get("expires_in", 86400))
        self._token = token
        self._expires_at = time.monotonic() + max(ttl - _REFRESH_MARGIN_SECONDS, 0)
        logger.debug("Issued new KB증권 access token: %s (ttl=%ss)", mask_secret(token), ttl)
