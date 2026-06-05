import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# We need to avoid loading real config
os.environ["PROXY_API_KEY"] = ""

from kiro.routes_setup import setup_router  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = FastAPI()
    app.state.setup_required = True
    app.state.account_manager = MagicMock()
    app.state.account_manager.reload_credentials = AsyncMock()

    creds_file = tmp_path / "creds.json"
    monkeypatch.setattr("kiro.routes_setup.ACCOUNTS_CONFIG_FILE", str(creds_file))

    app.include_router(setup_router)
    yield TestClient(app), tmp_path, creds_file


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


def test_setup_post_creates_config_and_redirects(client):
    test_client, tmp_path, creds_file = client

    with patch("pathlib.Path.cwd", return_value=tmp_path):
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


def test_admin_page_redirects_to_setup_when_required(client):
    test_client, _, _ = client
    response = test_client.get("/admin", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/setup" in response.headers["location"]


def test_admin_page_renders_when_setup_complete(client):
    test_client, _, creds_file = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([{"type": "refresh_token", "refresh_token": "abc"}]))

    response = test_client.get("/admin")
    assert response.status_code == 200
    assert "Account Manager" in response.text
    assert "refresh_token" in response.text


def test_add_account_endpoint_writes_file_and_reloads(client):
    test_client, tmp_path, creds_file = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([]))

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        response = test_client.post(
            "/admin/api/accounts",
            data={
                "auth_type": "refresh_token",
                "auth_value": "new-token-xyz",
            },
            follow_redirects=False,
        )

    assert response.status_code in (302, 303)
    accounts = json.loads(creds_file.read_text())
    assert len(accounts) == 1
    assert accounts[0]["refresh_token"] == "new-token-xyz"
    test_client.app.state.account_manager.reload_credentials.assert_awaited()


def test_delete_account_removes_entry_and_reloads(client):
    test_client, tmp_path, creds_file = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([
        {"type": "refresh_token", "refresh_token": "first"},
        {"type": "refresh_token", "refresh_token": "second"},
    ]))

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        response = test_client.post(
            "/admin/api/accounts/delete/0",
            follow_redirects=False,
        )

    assert response.status_code in (302, 303)
    accounts = json.loads(creds_file.read_text())
    assert len(accounts) == 1
    assert accounts[0]["refresh_token"] == "second"
    test_client.app.state.account_manager.reload_credentials.assert_awaited()


def test_delete_last_account_enters_setup_mode(client):
    test_client, tmp_path, creds_file = client
    test_client.app.state.setup_required = False
    creds_file.write_text(json.dumps([{"type": "refresh_token", "refresh_token": "only"}]))

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        response = test_client.post(
            "/admin/api/accounts/delete/0",
            follow_redirects=False,
        )

    assert response.status_code in (302, 303)
    assert test_client.app.state.setup_required is True
    assert not creds_file.exists() or json.loads(creds_file.read_text()) == []
