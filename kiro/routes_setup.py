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
WebUI routes: Setup Wizard and Admin Dashboard.

Provides:
- `api_setup_guard_middleware`: blocks /v1/* access until setup completes.
- `setup_router`: FastAPI router with /setup and /admin endpoints.
"""

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from loguru import logger

from kiro.config import ACCOUNTS_CONFIG_FILE


# ==================================================================================================
# Middleware
# ==================================================================================================

async def api_setup_guard_middleware(request: Request, call_next):
    """
    Block access to /v1/* endpoints if setup is required.

    When the gateway is unconfigured (no credentials.json, no .env), this
    middleware returns a 403 with a helpful message pointing the user to
    the /setup page instead of letting requests fail with cryptic errors.

    Args:
        request: Incoming HTTP request.
        call_next: Next middleware/handler in the chain.

    Returns:
        Either a 403 JSON response (when setup required) or the result of
        `call_next(request)`.
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


# ==================================================================================================
# Router
# ==================================================================================================

setup_router = APIRouter(tags=["WebUI"])


def get_html_template(title: str, content: str) -> str:
    """
    Build a complete HTML page using Tailwind CSS.

    Args:
        title: Page title shown in the browser tab.
        content: Body content (already wrapped in a card div).

    Returns:
        A full HTML document string.
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


@setup_router.get("/", response_class=RedirectResponse)
async def root_redirect(request: Request):
    """
    Redirect / to /setup (when setup required) or /admin (otherwise).

    Args:
        request: Incoming HTTP request.

    Returns:
        RedirectResponse to the appropriate page.
    """
    if getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/setup")
    return RedirectResponse(url="/admin")


@setup_router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    """
    Render the Setup Wizard page.

    Redirects to /admin if setup is already complete.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTMLResponse with the setup form, or RedirectResponse to /admin.
    """
    if not getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/admin")

    content = """
<h2 class="text-2xl font-bold mb-2 text-gray-800">Kiro Gateway Setup</h2>
<p class="text-sm text-gray-600 mb-6">Configure your gateway to get started.</p>

<form action="/setup" method="post" class="space-y-4">
    <div>
        <label class="block text-sm font-medium text-gray-700">Admin Password (PROXY_API_KEY)</label>
        <input type="password" name="api_key" required minlength="8"
               class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500"
               placeholder="Choose a strong password">
        <p class="text-xs text-gray-500 mt-1">Minimum 8 characters. You'll use this to access the dashboard.</p>
    </div>

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
            class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
        Save and Start Gateway
    </button>
</form>

<script>
function toggleAuthField() {
    const type = document.getElementById('auth_type').value;
    const rtField = document.getElementById('refresh_token_field');
    const sqlField = document.getElementById('sqlite_field');
    const rtInput = rtField.querySelector('input');
    const sqlInput = sqlField.querySelector('input');

    if (type === 'sqlite') {
        rtField.style.display = 'none';
        sqlField.style.display = 'block';
        rtInput.disabled = true;
        sqlInput.disabled = false;
        sqlInput.name = 'auth_value';
        rtInput.name = 'auth_value_rt';
    } else {
        rtField.style.display = 'block';
        sqlField.style.display = 'none';
        rtInput.disabled = false;
        sqlInput.disabled = true;
        rtInput.name = 'auth_value';
        sqlInput.name = 'auth_value_sqlite';
    }
}
</script>
"""
    return get_html_template("Setup Wizard", content)


@setup_router.post("/setup")
async def process_setup(
    request: Request,
    api_key: str = Form(...),
    auth_type: str = Form(...),
    auth_value: str = Form(None),
    auth_value_rt: str = Form(None),
    auth_value_sqlite: str = Form(None),
):
    """
    Process the setup form: write .env, write credentials.json, hot-reload.

    Only one of `auth_value` / `auth_value_rt` / `auth_value_sqlite` is
    populated thanks to client-side JavaScript toggling field names.

    Args:
        request: Incoming HTTP request.
        api_key: Chosen admin password.
        auth_type: Either "refresh_token" or "sqlite".
        auth_value: Active value (renamed by JS).
        auth_value_rt: Refresh token value (disabled field, kept for fallback).
        auth_value_sqlite: SQLite path value (disabled field, kept for fallback).

    Returns:
        RedirectResponse to /admin on success, or HTMLResponse with error.
    """
    actual_value = auth_value or auth_value_rt or auth_value_sqlite
    if not actual_value:
        return HTMLResponse(
            content="<h1>Error</h1><p>No token or path provided.</p>",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 1. Update .env file
    env_path = Path(".env")
    env_content = env_path.read_text() if env_path.exists() else ""

    if re.search(r"^PROXY_API_KEY=.*$", env_content, re.MULTILINE):
        env_content = re.sub(
            r"^PROXY_API_KEY=.*$",
            f'PROXY_API_KEY="{api_key}"',
            env_content,
            flags=re.MULTILINE,
        )
    else:
        env_content += f'\nPROXY_API_KEY="{api_key}"\n'

    if "ACCOUNT_SYSTEM" not in env_content:
        env_content += "ACCOUNT_SYSTEM=true\n"
    else:
        env_content = re.sub(
            r"^ACCOUNT_SYSTEM=.*$",
            "ACCOUNT_SYSTEM=true",
            env_content,
            flags=re.MULTILINE,
        )

    env_path.write_text(env_content)

    os.environ["PROXY_API_KEY"] = api_key
    os.environ["ACCOUNT_SYSTEM"] = "true"

    # 2. Update credentials.json
    creds = []
    if auth_type == "refresh_token":
        creds.append({"type": "refresh_token", "refresh_token": actual_value})
    elif auth_type == "sqlite":
        creds.append({"type": "sqlite", "path": actual_value})

    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    creds_path.write_text(json.dumps(creds, indent=2))
    logger.info(f"Setup: wrote {len(creds)} account(s) to {creds_path}")

    # 3. Hot reload
    request.app.state.setup_required = False
    if hasattr(request.app.state, "account_manager") and request.app.state.account_manager is not None:
        try:
            await request.app.state.account_manager.reload_credentials()
        except Exception as e:
            logger.error(f"Hot reload failed: {e}")

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@setup_router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """
    Render the Account Manager Dashboard.

    Redirects to /setup if setup is not yet complete.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTMLResponse with the admin dashboard, or RedirectResponse to /setup.
    """
    if getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/setup")

    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    accounts = json.loads(creds_path.read_text()) if creds_path.exists() else []

    accounts_html = ""
    for i, acc in enumerate(accounts):
        acc_type = acc.get("type", "Unknown")
        acc_value = acc.get("refresh_token", acc.get("path", ""))
        display_value = acc_value[:20] + "..." if len(acc_value) > 20 else acc_value

        accounts_html += f"""
<div class="border border-gray-200 p-4 rounded-md mb-2 flex justify-between items-center">
    <div class="flex-1 min-w-0">
        <span class="font-semibold text-gray-800">{acc_type}</span>
        <span class="text-sm text-gray-500 block font-mono truncate">{display_value}</span>
    </div>
    <form action="/admin/api/accounts/delete/{i}" method="post" class="ml-2">
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

<div class="border-t pt-6 mt-6 text-center">
    <p class="text-xs text-gray-400">Gateway is running. API endpoints at <code>/v1/</code> are live.</p>
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
    return get_html_template("Admin Dashboard", content)


@setup_router.post("/admin/api/accounts")
async def add_account(
    request: Request,
    auth_type: str = Form(...),
    auth_value: str = Form(None),
    auth_value_rt: str = Form(None),
    auth_value_sqlite: str = Form(None),
):
    """
    Append a new account to credentials.json and trigger hot-reload.

    Args:
        request: Incoming HTTP request.
        auth_type: Either "refresh_token" or "sqlite".
        auth_value: Active value (renamed by JS).
        auth_value_rt: Refresh token value (disabled field).
        auth_value_sqlite: SQLite path value (disabled field).

    Returns:
        RedirectResponse to /admin on success, or HTMLResponse with error.
    """
    actual_value = auth_value or auth_value_rt or auth_value_sqlite
    if not actual_value:
        return HTMLResponse(
            content="<h1>Error</h1><p>No value provided.</p>",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    accounts = json.loads(creds_path.read_text()) if creds_path.exists() else []

    if auth_type == "refresh_token":
        accounts.append({"type": "refresh_token", "refresh_token": actual_value})
    elif auth_type == "sqlite":
        accounts.append({"type": "sqlite", "path": actual_value})

    creds_path.write_text(json.dumps(accounts, indent=2))
    logger.info(f"Added account #{len(accounts)} ({auth_type})")

    if hasattr(request.app.state, "account_manager") and request.app.state.account_manager is not None:
        try:
            await request.app.state.account_manager.reload_credentials()
        except Exception as e:
            logger.error(f"Hot reload after add failed: {e}")

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@setup_router.post("/admin/api/accounts/delete/{index}")
async def delete_account(request: Request, index: int):
    """
    Remove an account from credentials.json and trigger hot-reload.

    If the last account is removed, the gateway re-enters setup mode.

    Args:
        request: Incoming HTTP request.
        index: Zero-based index of the account to delete.

    Returns:
        RedirectResponse to /admin.
    """
    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    if not creds_path.exists():
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    accounts = json.loads(creds_path.read_text())
    if 0 <= index < len(accounts):
        removed = accounts.pop(index)
        creds_path.write_text(json.dumps(accounts, indent=2))
        logger.info(f"Deleted account #{index} ({removed.get('type')})")

        if not accounts:
            request.app.state.setup_required = True
            logger.warning("All accounts deleted. Entering setup mode.")

    if hasattr(request.app.state, "account_manager") and request.app.state.account_manager is not None:
        try:
            await request.app.state.account_manager.reload_credentials()
        except Exception as e:
            logger.error(f"Hot reload after delete failed: {e}")

    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
