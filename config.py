import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

DEFAULT_BASE_URL = "https://developer.kbsec.com:32484"
DEFAULT_TIMEOUT_SECONDS = 10.0
_TRUTHY_VALUES = {"1", "true", "yes", "on"}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    app_key: str
    app_secret: str
    base_url: str
    timeout_seconds: float
    trading_enabled: bool


def load_config() -> Config:
    app_key = os.environ.get("KBSEC_APP_KEY")
    app_secret = os.environ.get("KBSEC_APP_SECRET")
    if not app_key:
        raise ConfigError("Missing required environment variable: KBSEC_APP_KEY")
    if not app_secret:
        raise ConfigError("Missing required environment variable: KBSEC_APP_SECRET")
    base_url = os.environ.get("KBSEC_BASE_URL", DEFAULT_BASE_URL)
    timeout_seconds = float(os.environ.get("KBSEC_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    trading_enabled = os.environ.get("KBSEC_ENABLE_TRADING", "false").strip().lower() in _TRUTHY_VALUES
    return Config(
        app_key=app_key,
        app_secret=app_secret,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        trading_enabled=trading_enabled,
    )
