# Web UI and Setup Wizard Design

## 1. Overview
Add a web-based Setup Wizard and Admin Dashboard to Kiro Gateway without weakening the existing API authentication model. The Web UI must support local single-host deployments and orchestrated Docker deployments such as Dokploy and Arcane, where platform-managed environment variables may be the source of truth.

## 2. Goals
- Allow first-run setup without crashing the process when credentials are missing.
- Protect `/admin` and all mutating Web UI routes with authenticated browser sessions.
- Keep OpenAI and Anthropic API authentication behavior unchanged.
- Persist account configuration and runtime account state across container recreation.
- Avoid relying on `.env` as a persistent runtime store in platform-managed Docker environments.

## 3. Runtime Behavior

### 3.1 Setup Mode
- The app starts in setup mode when either:
  - `PROXY_API_KEY` is missing or still uses the insecure default value.
  - No valid accounts are configured.
- In setup mode, `/v1/*` routes return `403` with a pointer to `/setup`.
- `/health`, `/setup`, `/login`, and other Web UI routes remain reachable.

### 3.2 Web UI Authentication
- Add `GET /login` and `POST /login`.
- `GET /admin` and all mutating Web UI routes require either:
  - A valid signed session cookie.
  - Or `Authorization: Bearer {PROXY_API_KEY}` as a fallback.
- Session cookies persist for 30 days.
- The session signature is derived from `PROXY_API_KEY`, so rotating the key invalidates old sessions automatically.

### 3.3 Setup Flow
- `GET /setup` renders the first-run wizard.
- `POST /setup`:
  - Stores account configuration in `credentials.json`.
  - Optionally stores `PROXY_API_KEY` in `.env` only when local env-managed mode is enabled.
  - Reloads `AccountManager` without restarting the process.
  - Creates a valid Web UI session and redirects to `/admin`.

## 4. Configuration Modes

### 4.1 Local Env-Managed Mode
- Intended for local installs and simple Docker runs.
- The Setup Wizard may write:
  - `PROXY_API_KEY`
  - `ACCOUNT_SYSTEM=true`
  into `.env`.

### 4.2 Platform-Managed Mode
- Intended for Dokploy, Arcane Git Sync, and similar orchestration environments.
- `PROXY_API_KEY` is treated as externally managed.
- The Setup Wizard must not overwrite `.env`.
- If `PROXY_API_KEY` is missing or insecure in this mode, the UI shows a blocking instruction telling the user to configure it in the platform.

### 4.3 Mode Selection
- Mode selection is explicit through configuration, not auto-detected from the platform.

## 5. Persistence Model
- `credentials.json` is the source of truth for Web UI-managed accounts.
- `state.json` stores runtime account state such as sticky selection and failure counters.
- For Docker deployments, both files should live on a persistent mount such as `/app/data`:
  - `ACCOUNTS_CONFIG_FILE=/app/data/credentials.json`
  - `ACCOUNTS_STATE_FILE=/app/data/state.json`
- `PROXY_API_KEY` should be managed by platform environment variables in Dokploy and Arcane Git Sync deployments.

## 6. Account Manager Behavior
- `AccountManager.reload_credentials()` must reuse the existing internal data model:
  - `_accounts`
  - `_credentials_config`
  - `_model_to_accounts`
  - `_current_account_index`
- Reload clears in-memory state, reloads credentials from disk, and initializes the first working account if one exists.
- Reloading to zero accounts must not crash the process; it should return the app to setup mode.

## 7. Docker and Deployment Guidance
- Default Docker deployment should use a named volume mounted to `/app/data`.
- `Dockerfile` should create `/app/data` and make it writable for the non-root runtime user.
- `docker-compose.yml` should set the account file paths into `/app/data`.
- Docs must explicitly warn that `.env` is not a reliable persistent store for Dokploy or Arcane Git Sync when those platforms regenerate or sync project files.

## 8. Testing
- Add or update unit tests for:
  - Web UI login and session validation.
  - Auth protection on `/admin` and mutating routes.
  - Setup mode API guard behavior.
  - Local env-managed vs platform-managed setup behavior.
  - `AccountManager.reload_credentials()` behavior with added and removed accounts.
  - Docker deployment defaults for persistent account files.

## 9. Non-Goals
- No changes to OpenAI or Anthropic API key validation semantics.
- No full frontend framework or SPA.
- No platform auto-detection for Dokploy, Arcane, or other orchestration systems.
