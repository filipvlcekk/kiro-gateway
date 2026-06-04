# Web UI and Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Setup Wizard and Account Manager Dashboard that runs inside the Kiro Gateway FastAPI application, allowing users to easily configure and manage tokens via a browser instead of manual file editing.

**Architecture:** 
- The app will start gracefully even without valid credentials by checking `app.state.setup_required`.
- A FastAPI middleware (API Guard) will intercept all API calls to `/v1/*` when `setup_required` is True, returning a 403 status with instructions to visit the Setup UI.
- The web UI will consist of simple FastAPI HTML endpoints rendering raw HTML with TailwindCSS via CDN.
- Config updates will write directly to `.env` (for PROXY_API_KEY) and `credentials.json` (for accounts), followed by an in-memory hot-reload of the `AccountManager` state.

**Tech Stack:** Python, FastAPI, TailwindCSS (CDN), HTML, JavaScript (Fetch API).

---

## Chunk 1: Modifying the Boot Sequence and API Guard

**Files:**
- Modify: `main.py`
- Modify: `kiro/account_manager.py`
- Create: `tests/unit/test_api_guard.py`

### Task 1: Update main.py to avoid hard crash and set setup_required flag

- [ ] **Step 1: Write the failing test** (or manually verify logic change)
Since `main.py` is the entry point, the main test is integration. Let's create `tests/unit/test_api_guard.py` to test the middleware behavior we will build. First, we write a test for the guard.

```python
# tests/unit/test_api_guard.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.routes_setup import api_setup_guard_middleware  # we'll create this module

app = FastAPI()
app.state.setup_required = True
app.middleware("http")(api_setup_guard_middleware)

@app.get("/v1/models")
async def models():
    return {"data": []}

@app.get("/health")
async def health():
    return {"status": "ok"}

def test_api_guard_blocks_v1_when_setup_required():
    client = TestClient(app)
    response = client.get("/v1/models")
    assert response.status_code == 403
    assert "Gateway requires configuration" in response.text
    assert "/setup" in response.text

def test_api_guard_allows_health_when_setup_required():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
```

- [ ] **Step 2: Create `kiro/routes_setup.py` with middleware logic**

```python
# kiro/routes_setup.py
import json
from fastapi import Request, Response
from fastapi.responses import JSONResponse

async def api_setup_guard_middleware(request: Request, call_next):
    """Blocks access to /v1/* endpoints if setup is required."""
    is_setup_required = getattr(request.app.state, "setup_required", False)
    
    if is_setup_required and request.url.path.startswith("/v1/"):
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "message": f"Gateway requires configuration. Please visit http://{request.url.hostname}:{request.url.port}/setup in your browser.",
                    "type": "setup_required_error",
                    "code": "setup_required"
                }
            }
        )
    
    return await call_next(request)
```

- [ ] **Step 3: Modify `main.py` to remove `raise RuntimeError` and inject state**
Locate the block handling `errors` in `main.py` (around line 303).
Change it from `raise RuntimeError(...)` to:
```python
    app.state.setup_required = False
    if errors or PROXY_API_KEY == "my-super-secret-password-123" or not PROXY_API_KEY:
        logger.warning("Configuration validation failed or default API key used. Enabling Setup Mode.")
        app.state.setup_required = True
        # Do not raise RuntimeError, let the app start in setup mode.
```
Add the middleware to `main.py`:
```python
from kiro.routes_setup import api_setup_guard_middleware
# ...
app.middleware("http")(api_setup_guard_middleware)
```

- [ ] **Step 4: Modify `lifespan` in `main.py` and `AccountManager` to not crash on load.**
In `main.py` lifespan (around line 498):
```python
        except Exception as e:
            logger.error(f"AccountManager initialization failed: {e}")
            if getattr(app.state, "setup_required", False):
                 logger.warning("Continuing in Setup Mode...")
            else:
                 raise RuntimeError("Failed to initialize any account")
```
Also ensure `AccountManager` can be instantiated without throwing errors if the file doesn't exist, by swallowing initial load errors if `setup_required` is active.

- [ ] **Step 5: Run tests and Commit**
Run `pytest tests/unit/test_api_guard.py -v`
Commit changes: `git commit -m "feat: add api setup guard middleware and prevent startup crash"`

---

## Chunk 2: Hot Reloading in Account Manager

**Files:**
- Modify: `kiro/account_manager.py`

### Task 1: Add `reload_credentials` method to `AccountManager`

- [ ] **Step 1: Write `reload_credentials` method**
In `kiro/account_manager.py`, add a new async method to `AccountManager`:
```python
    async def reload_credentials(self) -> None:
        """Reloads credentials.json and re-initializes accounts dynamically without restarting."""
        async with self._lock:
            logger.info("Hot-reloading credentials...")
            # Clear existing accounts
            self.accounts = []
            self._current_index = 0
            
            # Re-read the file
            self._load_accounts()
            
            # Re-initialize the first account if any exist
            if self.accounts:
                try:
                    await self._initialize_account(self.accounts[0])
                except Exception as e:
                    logger.error(f"Failed to initialize first account after reload: {e}")
```

- [ ] **Step 2: Commit**
`git commit -m "feat: add hot-reload capability to account manager"`

---

## Chunk 3: Building the Web UI Routes (Setup and Admin)

**Files:**
- Modify: `kiro/routes_setup.py`
- Modify: `main.py` (to register the router)

### Task 1: Implement GET and POST endpoints for `/setup` and `/admin`

- [ ] **Step 1: Add HTML templates and endpoints in `kiro/routes_setup.py`**
Use `APIRouter`. Create a basic HTML string with Tailwind CSS for `/setup`.

```python
from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from kiro.config import ACCOUNTS_CONFIG_FILE
import os
import json
from pathlib import Path
from loguru import logger

setup_router = APIRouter(tags=["WebUI"])

def get_html_template(title: str, content: str) -> str:
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
    if getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/setup")
    return RedirectResponse(url="/admin")

@setup_router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    if not getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/admin")
        
    content = """
    <h2 class="text-2xl font-bold mb-6 text-gray-800">Kiro Gateway Setup</h2>
    <form action="/setup" method="post" class="space-y-4">
        <div>
            <label class="block text-sm font-medium text-gray-700">Admin Password (PROXY_API_KEY)</label>
            <input type="password" name="api_key" required class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-2 border focus:ring-blue-500 focus:border-blue-500">
            <p class="text-xs text-gray-500 mt-1">Set a strong password to protect your gateway.</p>
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700">Auth Method</label>
            <select name="auth_type" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-2 border">
                <option value="refresh_token">Refresh Token (Kiro IDE)</option>
                <option value="sqlite">SQLite DB (AWS SSO / kiro-cli)</option>
            </select>
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700">Token or DB Path</label>
            <input type="text" name="auth_value" required class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-2 border">
        </div>
        <button type="submit" class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700">
            Save and Start Gateway
        </button>
    </form>
    """
    return get_html_template("Setup Wizard", content)

@setup_router.post("/setup")
async def process_setup(request: Request, api_key: str = Form(...), auth_type: str = Form(...), auth_value: str = Form(...)):
    # 1. Update .env file
    env_path = Path(".env")
    env_content = env_path.read_text() if env_path.exists() else ""
    
    if "PROXY_API_KEY=" in env_content:
        import re
        env_content = re.sub(r'PROXY_API_KEY=.*', f'PROXY_API_KEY="{api_key}"', env_content)
    else:
        env_content += f'\nPROXY_API_KEY="{api_key}"\nACCOUNT_SYSTEM=true\n'
    
    env_path.write_text(env_content)
    os.environ["PROXY_API_KEY"] = api_key
    os.environ["ACCOUNT_SYSTEM"] = "true"
    
    # 2. Update credentials.json
    creds = []
    if auth_type == "refresh_token":
        creds.append({"type": "refresh_token", "refresh_token": auth_value})
    elif auth_type == "sqlite":
        creds.append({"type": "sqlite", "path": auth_value})
        
    Path(ACCOUNTS_CONFIG_FILE).write_text(json.dumps(creds, indent=2))
    
    # 3. Hot Reload
    request.app.state.setup_required = False
    await request.app.state.account_manager.reload_credentials()
    
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
```

- [ ] **Step 2: Implement `/admin` page**
Add to `kiro/routes_setup.py`. This page requires the user to pass the API Key (via basic auth, cookie, or simple form if not authed). For simplicity, let's use a very basic cookie auth or form auth.

```python
# add to kiro/routes_setup.py
@setup_router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    if getattr(request.app.state, "setup_required", False):
        return RedirectResponse(url="/setup")
        
    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    accounts = json.loads(creds_path.read_text()) if creds_path.exists() else []
    
    accounts_html = ""
    for i, acc in enumerate(accounts):
        accounts_html += f"""
        <div class="border p-4 rounded-md mb-2 flex justify-between items-center">
            <div>
                <span class="font-bold">{acc.get('type', 'Unknown')}</span>
                <span class="text-sm text-gray-500 block">{acc.get('refresh_token', acc.get('path', ''))[:15]}...</span>
            </div>
            <form action="/admin/api/accounts/delete/{i}" method="post">
                <button type="submit" class="text-red-600 hover:text-red-800">Delete</button>
            </form>
        </div>
        """
        
    content = f"""
    <h2 class="text-2xl font-bold mb-6 text-gray-800">Account Manager</h2>
    <div class="mb-6">
        <h3 class="text-lg font-semibold mb-2">Configured Accounts</h3>
        {accounts_html if accounts_html else "<p class='text-gray-500'>No accounts configured.</p>"}
    </div>
    
    <div class="border-t pt-4">
        <h3 class="text-lg font-semibold mb-2">Add New Account</h3>
        <form action="/admin/api/accounts" method="post" class="space-y-4">
            <div>
                <select name="auth_type" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-2 border">
                    <option value="refresh_token">Refresh Token</option>
                    <option value="sqlite">SQLite DB</option>
                </select>
            </div>
            <div>
                <input type="text" name="auth_value" placeholder="Token or Path" required class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-2 border">
            </div>
            <button type="submit" class="w-full bg-green-600 text-white p-2 rounded-md hover:bg-green-700">Add Account</button>
        </form>
    </div>
    """
    return get_html_template("Admin Dashboard", content)

@setup_router.post("/admin/api/accounts")
async def add_account(request: Request, auth_type: str = Form(...), auth_value: str = Form(...)):
    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    accounts = json.loads(creds_path.read_text()) if creds_path.exists() else []
    
    if auth_type == "refresh_token":
        accounts.append({"type": "refresh_token", "refresh_token": auth_value})
    elif auth_type == "sqlite":
        accounts.append({"type": "sqlite", "path": auth_value})
        
    creds_path.write_text(json.dumps(accounts, indent=2))
    await request.app.state.account_manager.reload_credentials()
    
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@setup_router.post("/admin/api/accounts/delete/{index}")
async def delete_account(request: Request, index: int):
    creds_path = Path(ACCOUNTS_CONFIG_FILE)
    if creds_path.exists():
        accounts = json.loads(creds_path.read_text())
        if 0 <= index < len(accounts):
            accounts.pop(index)
            creds_path.write_text(json.dumps(accounts, indent=2))
            
            # Check if all accounts deleted
            if not accounts:
                request.app.state.setup_required = True
            
            await request.app.state.account_manager.reload_credentials()
            
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
```

- [ ] **Step 3: Register the router in `main.py`**
In `main.py`, import the router and include it.
```python
from kiro.routes_setup import setup_router
# ... near the bottom with other routers
app.include_router(setup_router)
```

- [ ] **Step 4: Verify syntax and Commit**
`git add main.py kiro/routes_setup.py kiro/account_manager.py tests/unit/test_api_guard.py`
`git commit -m "feat: implement webui setup wizard and admin dashboard"`
