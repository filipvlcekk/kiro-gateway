# Web UI and Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Setup Wizard and Admin Dashboard secure, persistence-safe for Docker deployments, and consistent with the existing account system and bootstrap flow.

**Architecture:** Keep the existing FastAPI Web UI surface, but tighten it around small helpers for session auth, setup mode evaluation, and environment file updates. Persist account files under `/app/data` for container deployments while supporting an explicit platform-managed mode where `PROXY_API_KEY` is controlled outside the app.

**Tech Stack:** Python, FastAPI, HTMLResponse, signed cookies, pytest, Docker Compose.

---

## Chunk 1: Fix Deployment Defaults

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing deployment tests**
- [ ] **Step 2: Run `python -m pytest tests/unit/test_config.py -k "TestContainerDeploymentFiles" -q` and confirm failure**
- [ ] **Step 3: Update Docker runtime defaults to use `/app/data`**
- [ ] **Step 4: Re-run `python -m pytest tests/unit/test_config.py -k "TestContainerDeploymentFiles" -q` and confirm pass**

## Chunk 2: Add Web UI Auth and Setup Mode Helpers

**Files:**
- Modify: `kiro/routes_setup.py`
- Test: `tests/unit/test_webui_routes.py`

- [ ] **Step 1: Write failing tests for `/login`, session cookie auth, and bearer fallback**
- [ ] **Step 2: Run the focused test subset and confirm the auth behavior is missing**
- [ ] **Step 3: Implement signed Web UI session helpers and route guards**
- [ ] **Step 4: Re-run the focused tests and confirm pass**

## Chunk 3: Support Env-Managed vs Platform-Managed Setup

**Files:**
- Modify: `kiro/config.py`
- Modify: `kiro/routes_setup.py`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_webui_routes.py`

- [ ] **Step 1: Write failing tests for explicit Web UI config mode handling**
- [ ] **Step 2: Add config flag for env-managed vs platform-managed setup**
- [ ] **Step 3: Implement `.env` writer helper only for env-managed mode**
- [ ] **Step 4: Implement blocking setup instructions when platform-managed mode lacks a secure `PROXY_API_KEY`**
- [ ] **Step 5: Re-run focused config and Web UI tests**

## Chunk 4: Align Bootstrap and Account Reload Behavior

**Files:**
- Modify: `main.py`
- Modify: `kiro/account_manager.py`
- Test: `tests/unit/test_account_manager.py`
- Test: `tests/unit/test_main_lifespan.py`

- [ ] **Step 1: Write failing tests for graceful startup in setup mode and zero-account reload behavior**
- [ ] **Step 2: Adjust setup state evaluation and `lifespan` flow without changing API auth semantics**
- [ ] **Step 3: Stabilize `AccountManager.reload_credentials()` around the existing internal data model**
- [ ] **Step 4: Re-run focused lifespan and account-manager tests**

## Chunk 5: Repair Docs and User-Facing Guidance

**Files:**
- Modify: `docs/superpowers/specs/2026-06-04-webui-setup-wizard-design.md`
- Modify: `docs/superpowers/plans/2026-06-04-webui-setup-wizard-plan.md`
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Update docs to match the actual route names, auth behavior, and Docker persistence model**
- [ ] **Step 2: Document Dokploy and Arcane guidance: platform-managed `PROXY_API_KEY`, persistent account volume**
- [ ] **Step 3: Re-read the docs for consistency with the implementation**

## Chunk 6: Final Verification

**Files:**
- Verify: `tests/unit/test_config.py`
- Verify: `tests/unit/test_webui_routes.py`
- Verify: `tests/unit/test_api_guard.py`
- Verify: `tests/unit/test_account_manager.py`
- Verify: `tests/unit/test_main_lifespan.py`

- [ ] **Step 1: Run the full focused verification command**
- [ ] **Step 2: Read the output and confirm all targeted tests pass**
- [ ] **Step 3: Summarize remaining risk, if any**
