import tools.auth as auth_tool


async def test_auth_revoke_token_returns_revoked_true(monkeypatch):
    async def fake_revoke_token() -> bool:
        return True

    monkeypatch.setattr(auth_tool, "revoke_token", fake_revoke_token)
    result = await auth_tool.auth_revoke_token()
    assert result == {"revoked": True}


async def test_auth_revoke_token_returns_revoked_false_without_cached_token(monkeypatch):
    async def fake_revoke_token() -> bool:
        return False

    monkeypatch.setattr(auth_tool, "revoke_token", fake_revoke_token)
    result = await auth_tool.auth_revoke_token()
    assert result == {"revoked": False}
