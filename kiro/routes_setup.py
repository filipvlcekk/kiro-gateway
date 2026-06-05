# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
WebUI routes: Setup Wizard, login, and Admin Dashboard.

Provides:
- `api_setup_guard_middleware`: blocks `/v1/*` access until setup completes
- `setup_router`: WebUI routes for setup, login, and account management
"""

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from collections.abc import Callable

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from loguru import logger

from kiro.config import ACCOUNTS_CONFIG_FILE, PROXY_API_KEY, WEBUI_CONFIG_MODE


INSECURE_DEFAULT_PROXY_API_KEY = "my-super-secret-password-123"
SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
WEBUI_ENV_FILE = Path(".env")


async def api_setup_guard_middleware(request: Request, call_next: Callable) -> Response:
    """
    Block access to `/v1/*` endpoints if setup is required.

    Args:
        request: Incoming HTTP request.
        call_next: Next middleware or route handler.

    Returns:
        Either a 403 JSON response for blocked API requests or the downstream response.
    """
    is_setup_required = getattr(request.app.state, "setup_required", False)

    if is_setup_required and request.url.path.startswith("/v1/"):
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "message": (
                        f"Gateway requires configuration. "
                        f"Please visit http://{request.url.hostname}:{request.url.port}/setup in your browser."
                    ),
                    "type": "setup_required_error",
                    "code": "setup_required",
                }
            },
        )

    return await call_next(request)


setup_router = APIRouter(tags=["WebUI"])


def _get_proxy_api_key() -> str:
    """
    Return the current effective WebUI/API secret.

    Returns:
        The active proxy API key, preferring runtime environment updates.
    """
    env_api_key = os.environ.get("PROXY_API_KEY")
    if env_api_key:
        return env_api_key
    return PROXY_API_KEY


def _has_secure_proxy_api_key() -> bool:
    """
    Check whether the current proxy API key is non-empty and not the insecure default.

    Returns:
        True when the current key is safe enough to use for WebUI auth.
    """
    api_key = _get_proxy_api_key()
    return bool(api_key and api_key != INSECURE_DEFAULT_PROXY_API_KEY)


def _is_platform_managed_mode() -> bool:
    """
    Check whether the WebUI should treat the proxy key as externally managed.

    Returns:
        True when `.env` must not be modified by the Setup Wizard.
    """
    return WEBUI_CONFIG_MODE == "platform_managed"


def _build_session_token(api_key: str) -> str:
    """
    Build a signed session token.

    Args:
        api_key: Secret used to sign the session.

    Returns:
        Signed token containing an expiry timestamp.
    """
    expires_at = int(time.time()) + SESSION_MAX_AGE_SECONDS
    payload = str(expires_at)
    signature = hmac.new(api_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _is_valid_session_token(token: str | None) -> bool:
    """
    Validate a signed session token.

    Args:
        token: Session cookie value.

    Returns:
        True when the token is well-formed, unexpired, and signed by the current key.
    """
    if not token:
        return False

    parts = token.split(".", 1)
    if len(parts) != 2:
        return False

    expires_at_raw, signature = parts
    if not expires_at_raw.isdigit():
        return False

    expires_at = int(expires_at_raw)
    if expires_at < int(time.time()):
        return False

    api_key = _get_proxy_api_key()
    expected_signature = hmac.new(
        api_key.encode("utf-8"),
        expires_at_raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def _is_webui_authenticated(request: Request) -> bool:
    """
    Check WebUI authentication via bearer header or signed session cookie.

    Args:
        request: Incoming HTTP request.

    Returns:
        True when the request is authenticated for WebUI use.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header == f"Bearer {_get_proxy_api_key()}":
        return True

    return _is_valid_session_token(request.cookies.get(SESSION_COOKIE_NAME))


def _set_session_cookie(response: Response, api_key: str) -> None:
    """
    Set the WebUI session cookie on a response.

    Args:
        response: Response object to mutate.
        api_key: Secret used to sign the session.
    """
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=_build_session_token(api_key),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )


def _write_env_settings(env_path: Path, api_key: str) -> None:
    """
    Update or create `.env` entries used by the local setup flow.

    Args:
        env_path: Target `.env` file path.
        api_key: Proxy API key to store.
    """
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    updates = {
        "PROXY_API_KEY": f'"{api_key}"',
        "ACCOUNT_SYSTEM": "true",
    }
    seen_keys: set[str] = set()
    output_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output_lines.append(line)
            continue

        key, _, _value = line.partition("=")
        if key in updates:
            output_lines.append(f"{key}={updates[key]}")
            seen_keys.add(key)
        else:
            output_lines.append(line)

    for key, value in updates.items():
        if key not in seen_keys:
            output_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def _render_page(title: str, content: str) -> str:
    """
    Build a complete HTML page using Tailwind CSS.

    Args:
        title: Browser title.
        content: Inner card content.

    Returns:
        Full HTML page markup.
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen flex items-center justify-center p-4">
    <div class="max-w-md w-full bg-white rounded-xl shadow-lg p-8">
        {content}
    </div>
</body>
</html>
"""


def _login_redirect() -> RedirectResponse:
    """
    Create a redirect to the WebUI login page.

    Returns:
        Redirect response pointing to `/login`.
    """
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


def _credentials_from_form(
    auth_type: str,
    auth_value: str | None,
    auth_value_rt: str | None,
    auth_value_sqlite: str | None,
) -> dict | None:
    """
    Convert setup/admin form input into a credentials.json entry.

    Args:
        auth_type: Selected credential type.
        auth_value: Active field value.
        auth_value_rt: Refresh token fallback field.
        auth_value_sqlite: SQLite path fallback field.

    Returns:
        A credentials entry dict or None if the form did not provide a usable value.
    """
    actual_value = auth_value or auth_value_rt or auth_value_sqlite
    if not actual_value:
        return None

    if auth_type == "refresh_token":
        return {"type": "refresh_token", "refresh_token": actual_value}
    if auth_type == "sqlite":
        return {"type": "sqlite", "path": actual_value}
    return None


@setup_router.get("/", response_class=RedirectResponse)
async def root_redirect(request: Request) -> RedirectResponse:
    """
    Redirect `/` to `/setup` or `/admin` based on setup state.

    Args:
        request: Incoming HTTP request.

    Returns:
        Redirect response.
    """
    if getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/setup")
    return RedirectResponse(url="/admin")


@setup_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Response:
    """
    Render the WebUI login page.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML login page or redirect if the user is already authenticated.
    """
    if getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/setup")

    if _is_webui_authenticated(request):
        return RedirectResponse(url="/admin")

    content = """
<h2 class="text-2xl font-bold mb-2 text-gray-800">Web UI Login</h2>
<p class="text-sm text-gray-600 mb-6">Enter your gateway admin password.</p>
<form action="/login" method="post" class="space-y-4">
    <div>
        <label class="block text-sm font-medium text-gray-700">Admin Password</label>
        <input type="password" name="api_key" required
               class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500">
    </div>
    <button type="submit"
            class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700">
        Sign In
    </button>
</form>
"""
    return HTMLResponse(content=_render_page("Web UI Login", content))


@setup_router.post("/login")
async def process_login(api_key: str = Form(...)) -> Response:
    """
    Authenticate a browser session for the WebUI.

    Args:
        api_key: Submitted admin password.

    Returns:
        Redirect to `/admin` with a session cookie, or 401 on invalid credentials.
    """
    if api_key != _get_proxy_api_key():
        return HTMLResponse(
            content=_render_page("Web UI Login", "<h2 class=\"text-xl font-bold\">Invalid admin password.</h2>"),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, _get_proxy_api_key())
    return response


@setup_router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request) -> Response:
    """
    Render the Setup Wizard page.

    Args:
        request: Incoming HTTP request.

    Returns:
        Setup page or redirect to `/admin` when setup is already complete.
    """
    if not getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/admin")

    if _is_platform_managed_mode() and not _has_secure_proxy_api_key():
        content = """
<h2 class="text-2xl font-bold mb-2 text-gray-800">Kiro Gateway Setup</h2>
<p class="text-sm text-gray-600 mb-4">The proxy API key must be configured outside the gateway.</p>
<p class="text-sm text-gray-600">Set <code>PROXY_API_KEY</code> in your Docker platform or environment manager, then restart the container and return here to add accounts.</p>
"""
        return HTMLResponse(content=_render_page("Setup Wizard", content))

    password_section = """
    <div>
        <label class="block text-sm font-medium text-gray-700">Admin Password (PROXY_API_KEY)</label>
        <input type="password" name="api_key" required minlength="8"
               class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500"
               placeholder="Choose a strong password">
        <p class="text-xs text-gray-500 mt-1">Minimum 8 characters. You'll use this to access the dashboard.</p>
    </div>
    """
    if _is_platform_managed_mode():
        password_section = """
    <div class="rounded-md bg-blue-50 border border-blue-200 p-3 text-sm text-blue-900">
        <p><strong>Platform-managed mode:</strong> the existing platform secret will be used for Web UI login.</p>
    </div>
    <input type="hidden" name="api_key" value="platform-managed">
    """

    content = f"""
<h2 class="text-2xl font-bold mb-2 text-gray-800">Kiro Gateway Setup</h2>
<p class="text-sm text-gray-600 mb-6">Configure your gateway to get started.</p>

<form action="/setup" method="post" class="space-y-4">
    {password_section}

    <div>
        <label class="block text-sm font-medium text-gray-700">Authentication Method</label>
        <select name="auth_type" id="auth_type" onchange="toggleAuthField()"
                class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm p-2">
            <option value="refresh_token">Refresh Token (Kiro IDE)</option>
            <option value="sqlite">SQLite Database (AWS SSO / kiro-cli)</option>
        </select>
    </div>

    <div id="refresh_token_field">
        <label class="block text-sm font-medium text-gray-700">Refresh Token</label>
        <input type="text" name="auth_value"
               class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm p-2 font-mono text-sm"
               placeholder="Paste your Kiro refresh token here">
    </div>

    <div id="sqlite_field" style="display:none;">
        <label class="block text-sm font-medium text-gray-700">SQLite Database Path</label>
        <input type="text" name="auth_value_sqlite" disabled
               class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm p-2 font-mono text-sm"
               placeholder="/path/to/data.sqlite3">
    </div>

    <button type="submit"
            class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700">
        Save and Start Gateway
    </button>
</form>

<script>
function toggleAuthField() {{
    const type = document.getElementById('auth_type').value;
    const rtField = document.getElementById('refresh_token_field');
    const sqlField = document.getElementById('sqlite_field');
    const rtInput = rtField.querySelector('input');
    const sqlInput = sqlField.querySelector('input');

    if (type === 'sqlite') {{
        rtField.style.display = 'none';
        sqlField.style.display = 'block';
        rtInput.disabled = true;
        sqlInput.disabled = false;
        sqlInput.name = 'auth_value';
        rtInput.name = 'auth_value_rt';
    }} else {{
        rtField.style.display = 'block';
        sqlField.style.display = 'none';
        rtInput.disabled = false;
        sqlInput.disabled = true;
        rtInput.name = 'auth_value';
        sqlInput.name = 'auth_value_sqlite';
    }}
}}
</script>
"""
    return HTMLResponse(content=_render_page("Setup Wizard", content))


@setup_router.post("/setup")
async def process_setup(
    request: Request,
    api_key: str = Form(...),
    auth_type: str = Form(...),
    auth_value: str = Form(None),
    auth_value_rt: str = Form(None),
    auth_value_sqlite: str = Form(None),
) -> Response:
    """
    Process the setup form.

    Args:
        request: Incoming HTTP request.
        api_key: Submitted admin password.
        auth_type: Selected account type.
        auth_value: Active value field.
        auth_value_rt: Refresh token fallback field.
        auth_value_sqlite: SQLite fallback field.

    Returns:
        Redirect to `/admin` on success or HTML error response on invalid input.
    """
    credentials_entry = _credentials_from_form(auth_type, auth_value, auth_value_rt, auth_value_sqlite)
    if credentials_entry is None:
        return HTMLResponse(content="<h1>Error</h1><p>No token or path provided.</p>", status_code=status.HTTP_400_BAD_REQUEST)

    if _is_platform_managed_mode() and not _has_secure_proxy_api_key():
        return HTMLResponse(
            content="<h1>Error</h1><p>PROXY_API_KEY must be configured outside the gateway in platform-managed mode.</p>",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    effective_api_key = _get_proxy_api_key()
    if not _is_platform_managed_mode():
        _write_env_settings(WEBUI_ENV_FILE, api_key)
        os.environ["PROXY_API_KEY"] = api_key
        os.environ["ACCOUNT_SYSTEM"] = "true"
        effective_api_key = api_key

    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    creds_path.write_text(json.dumps([credentials_entry], indent=2), encoding="utf-8")
    logger.info(f"Setup: wrote 1 account to {creds_path}")

    if hasattr(request.app.state, "account_manager") and request.app.state.account_manager is not None:
        await request.app.state.account_manager.reload_credentials()

    request.app.state.setup_required = False
    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, effective_api_key)
    return response


@setup_router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> Response:
    """
    Render the Account Manager Dashboard.

    Args:
        request: Incoming HTTP request.

    Returns:
        Authenticated dashboard or redirect to `/setup` or `/login`.
    """
    if getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/setup")

    if not _is_webui_authenticated(request):
        return _login_redirect()

    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    accounts = json.loads(creds_path.read_text(encoding="utf-8")) if creds_path.exists() else []

    accounts_html = ""
    for index, account in enumerate(accounts):
        account_type = account.get("type", "Unknown")
        account_value = account.get("refresh_token", account.get("path", ""))
        display_value = account_value[:20] + "..." if len(account_value) > 20 else account_value
        accounts_html += f"""
<div class="border border-gray-200 p-4 rounded-md mb-2 flex justify-between items-center">
    <div class="flex-1 min-w-0">
        <span class="font-semibold text-gray-800">{account_type}</span>
        <span class="text-sm text-gray-500 block font-mono truncate">{display_value}</span>
    </div>
    <form action="/admin/api/accounts/delete/{index}" method="post" class="ml-2">
        <button type="submit"
                onclick="return confirm('Delete this account?')"
                class="text-red-600 hover:text-red-800 text-sm font-medium">
            Delete
        </button>
    </form>
</div>
"""

    if not accounts:
        accounts_html = '<p class="text-gray-500 italic">No accounts configured.</p>'

    content = f"""
<h2 class="text-2xl font-bold mb-2 text-gray-800">Account Manager</h2>
<p class="text-sm text-gray-600 mb-6">Manage your Kiro authentication tokens.</p>

<div class="mb-6">
    <h3 class="text-lg font-semibold mb-3 text-gray-700">Configured Accounts ({len(accounts)})</h3>
    {accounts_html}
</div>

<div class="border-t pt-6">
    <h3 class="text-lg font-semibold mb-3 text-gray-700">Add New Account</h3>
    <form action="/admin/api/accounts" method="post" class="space-y-3">
        <div>
            <select name="auth_type" id="admin_auth_type" onchange="toggleAdminField()"
                    class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm p-2">
                <option value="refresh_token">Refresh Token</option>
                <option value="sqlite">SQLite Database</option>
            </select>
        </div>
        <div id="admin_rt_field">
            <input type="text" name="auth_value"
                   class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm p-2 font-mono text-sm"
                   placeholder="Paste refresh token">
        </div>
        <div id="admin_sql_field" style="display:none;">
            <input type="text" name="auth_value_sqlite" disabled
                   class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm p-2 font-mono text-sm"
                   placeholder="/path/to/data.sqlite3">
        </div>
        <button type="submit"
                class="w-full bg-green-600 text-white py-2 px-4 rounded-md hover:bg-green-700 font-medium">
            Add Account
        </button>
    </form>
</div>

<script>
function toggleAdminField() {{
    const type = document.getElementById('admin_auth_type').value;
    const rtField = document.getElementById('admin_rt_field');
    const sqlField = document.getElementById('admin_sql_field');
    const rtInput = rtField.querySelector('input');
    const sqlInput = sqlField.querySelector('input');

    if (type === 'sqlite') {{
        rtField.style.display = 'none';
        sqlField.style.display = 'block';
        rtInput.disabled = true;
        sqlInput.disabled = false;
        sqlInput.name = 'auth_value';
        rtInput.name = 'auth_value_rt';
    }} else {{
        rtField.style.display = 'block';
        sqlField.style.display = 'none';
        rtInput.disabled = false;
        sqlInput.disabled = true;
        rtInput.name = 'auth_value';
        sqlInput.name = 'auth_value_sqlite';
    }}
}}
</script>
"""
    return HTMLResponse(content=_render_page("Admin Dashboard", content))


@setup_router.post("/admin/api/accounts")
async def add_account(
    request: Request,
    auth_type: str = Form(...),
    auth_value: str = Form(None),
    auth_value_rt: str = Form(None),
    auth_value_sqlite: str = Form(None),
) -> Response:
    """
    Append a new account to `credentials.json`.

    Args:
        request: Incoming HTTP request.
        auth_type: Selected account type.
        auth_value: Active value field.
        auth_value_rt: Refresh token fallback field.
        auth_value_sqlite: SQLite fallback field.

    Returns:
        Redirect to `/admin` or `/login`.
    """
    if not _is_webui_authenticated(request):
        return _login_redirect()

    credentials_entry = _credentials_from_form(auth_type, auth_value, auth_value_rt, auth_value_sqlite)
    if credentials_entry is None:
        return HTMLResponse(content="<h1>Error</h1><p>No value provided.</p>", status_code=status.HTTP_400_BAD_REQUEST)

    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    accounts = json.loads(creds_path.read_text(encoding="utf-8")) if creds_path.exists() else []
    accounts.append(credentials_entry)
    creds_path.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
    logger.info(f"Added account #{len(accounts)} ({auth_type})")

    if hasattr(request.app.state, "account_manager") and request.app.state.account_manager is not None:
        await request.app.state.account_manager.reload_credentials()

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@setup_router.post("/admin/api/accounts/delete/{index}")
async def delete_account(request: Request, index: int) -> Response:
    """
    Remove an account from `credentials.json`.

    Args:
        request: Incoming HTTP request.
        index: Zero-based account index.

    Returns:
        Redirect to `/admin` or `/login`.
    """
    if not _is_webui_authenticated(request):
        return _login_redirect()

    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    if not creds_path.exists():
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    accounts = json.loads(creds_path.read_text(encoding="utf-8"))
    if 0 <= index < len(accounts):
        removed = accounts.pop(index)
        creds_path.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
        logger.info(f"Deleted account #{index} ({removed.get('type')})")
        if not accounts:
            request.app.state.setup_required = True

    if hasattr(request.app.state, "account_manager") and request.app.state.account_manager is not None:
        await request.app.state.account_manager.reload_credentials()

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
