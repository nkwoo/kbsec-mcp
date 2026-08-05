import pytest

from config import ConfigError, load_config


def test_load_config_reads_required_and_default_values(monkeypatch):
    monkeypatch.setenv("KBSEC_APP_KEY", "test-key")
    monkeypatch.setenv("KBSEC_APP_SECRET", "test-secret")
    monkeypatch.delenv("KBSEC_BASE_URL", raising=False)
    monkeypatch.delenv("KBSEC_TIMEOUT_SECONDS", raising=False)

    config = load_config()

    assert config.app_key == "test-key"
    assert config.app_secret == "test-secret"
    assert config.base_url == "https://developer.kbsec.com:32484"
    assert config.timeout_seconds == 10.0


def test_load_config_respects_overrides(monkeypatch):
    monkeypatch.setenv("KBSEC_APP_KEY", "k")
    monkeypatch.setenv("KBSEC_APP_SECRET", "s")
    monkeypatch.setenv("KBSEC_BASE_URL", "https://example.test")
    monkeypatch.setenv("KBSEC_TIMEOUT_SECONDS", "5")

    config = load_config()

    assert config.base_url == "https://example.test"
    assert config.timeout_seconds == 5.0


def test_load_config_raises_when_app_key_missing(monkeypatch):
    monkeypatch.delenv("KBSEC_APP_KEY", raising=False)
    monkeypatch.setenv("KBSEC_APP_SECRET", "s")

    with pytest.raises(ConfigError):
        load_config()


def test_load_config_raises_when_app_secret_missing(monkeypatch):
    monkeypatch.setenv("KBSEC_APP_KEY", "k")
    monkeypatch.delenv("KBSEC_APP_SECRET", raising=False)

    with pytest.raises(ConfigError):
        load_config()
