import pytest

from config import ConfigError, load_config


def test_load_config_reads_required_and_default_values(monkeypatch):
    monkeypatch.setenv("KBSEC_APP_KEY", "test-key")
    monkeypatch.setenv("KBSEC_APP_SECRET", "test-secret")
    monkeypatch.delenv("KBSEC_BASE_URL", raising=False)
    monkeypatch.delenv("KBSEC_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("KBSEC_ENABLE_TRADING", raising=False)

    config = load_config()

    assert config.app_key == "test-key"
    assert config.app_secret == "test-secret"
    assert config.base_url == "https://developer.kbsec.com:32484"
    assert config.timeout_seconds == 10.0
    assert config.trading_enabled is False


@pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "on"])
def test_load_config_parses_truthy_trading_flag(monkeypatch, value):
    monkeypatch.setenv("KBSEC_APP_KEY", "k")
    monkeypatch.setenv("KBSEC_APP_SECRET", "s")
    monkeypatch.setenv("KBSEC_ENABLE_TRADING", value)

    config = load_config()

    assert config.trading_enabled is True


@pytest.mark.parametrize("value", ["false", "False", "0", "no", "off", ""])
def test_load_config_parses_falsy_trading_flag(monkeypatch, value):
    monkeypatch.setenv("KBSEC_APP_KEY", "k")
    monkeypatch.setenv("KBSEC_APP_SECRET", "s")
    monkeypatch.setenv("KBSEC_ENABLE_TRADING", value)

    config = load_config()

    assert config.trading_enabled is False


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
