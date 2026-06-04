# Web UI and Setup Wizard Design

## 1. Overview
Add a web-based Setup Wizard and Admin Dashboard to Kiro Gateway. This allows users, especially those running in Docker, to easily configure their `PROXY_API_KEY` and manage Kiro authentication tokens (accounts) without manually editing files.

## 2. Architecture Changes

### 2.1 Boot Sequence (`main.py` & `AccountManager`)
- **No Hard Crash:** Remove the startup validation that throws `RuntimeError` on missing credentials.
- **State Detection:** Introduce `app.state.setup_required`. Evaluates to `True` if `PROXY_API_KEY` is missing/default (e.g., "my-super-secret-password-123") OR no valid accounts are configured.

### 2.2 API Guard
- Intercept all `/v1/*` routes (OpenAI/Anthropic compatible endpoints).
- If `setup_required` is `True`, return `403 Forbidden` with a JSON message directing the user to `http://<host>:<port>/setup`.

### 2.3 Web UI (`kiro/routes_webui.py`)
- **Tech Stack:** FastAPI `HTMLResponse` and JSON endpoints. Frontend will use raw HTML with TailwindCSS via CDN for styling to keep it lightweight.
- **Routes:**
    - `GET /`: Redirects to `/setup` if needed, otherwise to `/admin`.
    - `GET /setup`: Wizard UI for initial setup (Admin Password & First Token).
    - `POST /setup`: Processes setup payload, writes config, triggers hot reload.
    - `GET /admin`: Dashboard UI. Requires authentication via session cookie or basic auth (matching `PROXY_API_KEY`).
    - `POST /admin/api/accounts`: Add a new account/token dynamically.
    - `DELETE /admin/api/accounts/{id}`: Remove an account.

### 2.4 Persistence & Hot Reload
- **Storage:**
    - `PROXY_API_KEY` and `ACCOUNT_SYSTEM=true` are written to `.env`.
    - Accounts/Tokens are written to `credentials.json` to fully utilize the multi-account circuit breaker logic.
- **Hot Reload:** `AccountManager` will expose a `reload_credentials()` method to apply changes immediately without requiring a Docker container restart.
