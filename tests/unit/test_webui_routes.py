import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.routes_setup import setup_router  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = FastAPI()
    app.state.setup_required = True
    app.state.account_manager = MagicMock()
    app.state.account_manager.reload_credentials = AsyncMock()

    creds_file = tmp_path / "creds.json"
    env_file = tmp_path / ".env"

    monkeypatch.setenv("PROXY_API_KEY", "")
    monkeypatch.setattr("kiro.routes_setup.ACCOUNTS_CONFIG_FILE", str(creds_file))
    monkeypatch.setattr("kiro.routes_setup.WEBUI_ENV_FILE", env_file)
    monkeypatch.setattr("kiro.routes_setup.PROXY_API_KEY", "test-admin-secret")
    monkeypatch.setattr("kiro.routes_setup.WEBUI_CONFIG_MODE", "env_managed")

    app.include_router(setup_router)
    yield TestClient(app), creds_file, env_file


def test_root_redirects_to_setup_in_setup_mode(client):
    test_client, _, _ = client
    response = test_client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/setup" in response.headers["location"]


def test_setup_page_renders(client):
    test_client, _, _ = client
    response = test_client.get("/setup")
    assert response.status_code == 200
    assert "Kiro Gateway Setup" in response.text
    assert "api_key" in response.text
    assert "auth_type" in response.text


def test_setup_page_shows_platform_managed_message_when_proxy_key_external(client, monkeypatch):
    test_client, _, _ = client
    monkeypatch.setattr("kiro.routes_setup.WEBUI_CONFIG_MODE", "platform_managed")
    monkeypatch.setattr("kiro.routes_setup.PROXY_API_KEY", "my-super-secret-password-123")

    response = test_client.get("/setup")

    assert response.status_code == 200
    assert "must be configured outside the gateway" in response.text


def test_setup_post_creates_config_redirects_and_sets_session_cookie(client):
    test_client, creds_file, env_file = client

    response = test_client.post(
        "/setup",
        data={
            "api_key": "my-secret-password-123",
            "auth_type": "refresh_token",
            "auth_value": "test-token-abc",
        },
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    assert creds_file.exists()
    accounts = json.loads(creds_file.read_text())
    assert len(accounts) == 1
    assert accounts[0]["refresh_token"] == "test-token-abc"
    assert env_file.exists()
    assert 'PROXY_API_KEY="my-secret-password-123"' in env_file.read_text()
    assert "session=" in response.headers["set-cookie"]


def test_setup_post_refuses_platform_managed_proxy_key_write_when_secret_missing(client, monkeypatch):
    test_client, creds_file, env_file = client
    monkeypatch.setattr("kiro.routes_setup.WEBUI_CONFIG_MODE", "platform_managed")
    monkeypatch.setattr("kiro.routes_setup.PROXY_API_KEY", "my-super-secret-password-123")

    response = test_client.post(
        "/setup",
        data={
            "api_key": "ignored-local-secret",
            "auth_type": "refresh_token",
            "auth_value": "test-token-abc",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert not creds_file.exists()
    assert not env_file.exists()


def test_login_page_renders_when_setup_complete(client):
    test_client, _, _ = client
    test_client.app.state.setup_required = False

    response = test_client.get("/login")

    assert response.status_code == 200
    assert "Web UI Login" in response.text


def test_admin_redirects_to_login_when_setup_complete_but_not_authenticated(client):
    test_client, _, creds_file = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([{"type": "refresh_token", "refresh_token": "abc"}]))

    response = test_client.get("/admin", follow_redirects=False)

    assert response.status_code in (302, 303, 307)
    assert "/login" in response.headers["location"]


def test_login_sets_session_cookie_and_allows_admin_access(client):
    test_client, creds_file, _ = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([{"type": "refresh_token", "refresh_token": "abc"}]))

    login_response = test_client.post(
        "/login",
        data={"api_key": "test-admin-secret"},
        follow_redirects=False,
    )

    assert login_response.status_code in (302, 303)
    assert "session=" in login_response.headers["set-cookie"]

    response = test_client.get("/admin")

    assert response.status_code == 200
    assert "Account Manager" in response.text


def test_admin_allows_authorization_header_fallback(client):
    test_client, creds_file, _ = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([{"type": "refresh_token", "refresh_token": "abc"}]))

    response = test_client.get(
        "/admin",
        headers={"Authorization": "Bearer test-admin-secret"},
    )

    assert response.status_code == 200
    assert "Account Manager" in response.text


def test_add_account_endpoint_requires_authentication(client):
    test_client, creds_file, _ = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([]))

    response = test_client.post(
        "/admin/api/accounts",
        data={"auth_type": "refresh_token", "auth_value": "new-token-xyz"},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303, 307)
    assert "/login" in response.headers["location"]


def test_add_account_endpoint_writes_file_and_reloads_with_bearer_auth(client):
    test_client, creds_file, _ = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([]))

    response = test_client.post(
        "/admin/api/accounts",
        data={
            "auth_type": "refresh_token",
            "auth_value": "new-token-xyz",
        },
        headers={"Authorization": "Bearer test-admin-secret"},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    accounts = json.loads(creds_file.read_text())
    assert len(accounts) == 1
    assert accounts[0]["refresh_token"] == "new-token-xyz"
    test_client.app.state.account_manager.reload_credentials.assert_awaited()


def test_delete_account_removes_entry_and_reloads_with_bearer_auth(client):
    test_client, creds_file, _ = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([
        {"type": "refresh_token", "refresh_token": "first"},
        {"type": "refresh_token", "refresh_token": "second"},
    ]))

    response = test_client.post(
        "/admin/api/accounts/delete/0",
        headers={"Authorization": "Bearer test-admin-secret"},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    accounts = json.loads(creds_file.read_text())
    assert len(accounts) == 1
    assert accounts[0]["refresh_token"] == "second"
    test_client.app.state.account_manager.reload_credentials.assert_awaited()


def test_delete_last_account_enters_setup_mode(client):
    test_client, creds_file, _ = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([{"type": "refresh_token", "refresh_token": "only"}]))

    response = test_client.post(
        "/admin/api/accounts/delete/0",
        headers={"Authorization": "Bearer test-admin-secret"},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    assert test_client.app.state.setup_required is True
    assert json.loads(creds_file.read_text()) == []
