# Python 3.11 Modernization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the project baseline to Python 3.11+, fix setup-mode startup locking, and modernize internal Python code without changing public API contracts.

**Architecture:** Apply changes in three passes: platform baseline, setup-state behavioral fix, and targeted Python 3.11 code cleanup. Keep the setup regression fix isolated and heavily verified before broadening into stylistic modernization.

**Tech Stack:** Python 3.11, FastAPI, pytest, pip-tools, pip-audit, Docker, GitHub Actions

---

## Chunk 1: Platform Baseline

### Task 1: Raise supported runtime to Python 3.11

**Files:**
- Modify: `Dockerfile`
- Modify: `.github/workflows/docker.yml`
- Modify: `README.md`
- Modify: `docs/*/README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update runtime declarations**
  - Change Docker base image to Python 3.11.
  - Change CI interpreter to Python 3.11.
  - Update version badges and text references from 3.10+ to 3.11+.

- [ ] **Step 2: Verify documentation consistency**
  - Search for remaining `3.10` support claims.
  - Keep non-support references such as numbered headings untouched.

### Task 2: Keep dependency locks aligned with Python 3.11

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `README.md`
- Modify: `tests/README.md`

- [ ] **Step 1: Regenerate hashed locks on Python 3.11**
  - Use `pip-compile --allow-unsafe --generate-hashes --strip-extras`.

- [ ] **Step 2: Verify strict install**
  - Run `python -m pip install --require-hashes -r requirements-dev.txt`.

## Chunk 2: Setup Regression Fix

### Task 3: Add failing tests for setup-state behavior

**Files:**
- Modify: `tests/unit/test_main_lifespan.py`
- Modify: `tests/unit/test_routes_openai.py`
- Modify: `tests/unit/test_routes_anthropic.py`
- Modify: `tests/integration/test_full_flow.py`

- [ ] **Step 1: Add tests that prove successful initialization clears setup mode**
- [ ] **Step 2: Add tests that protected routes do not return setup 403 when config is valid**
- [ ] **Step 3: Run only the new/affected tests and confirm they fail for the current bug**

### Task 4: Fix runtime setup-state handling

**Files:**
- Modify: `main.py`
- Modify: `kiro/routes_setup.py` only if middleware or helper behavior must be adjusted

- [ ] **Step 1: Remove or reduce import-time setup-state lock-in**
- [ ] **Step 2: Explicitly set `app.state.setup_required = False` after successful account initialization**
- [ ] **Step 3: Keep failure path setting `True`**
- [ ] **Step 4: Re-run targeted route/lifespan/integration tests**

### Task 5: Remove test import side effects

**Files:**
- Modify: `tests/unit/test_webui_routes.py`
- Modify: `tests/conftest.py` if a safer global test key fixture is needed

- [ ] **Step 1: Remove top-level environment mutation at test module import time**
- [ ] **Step 2: Move WebUI auth environment setup into fixtures or monkeypatch blocks**
- [ ] **Step 3: Re-run the affected route and WebUI tests**

## Chunk 3: Active Modernization

### Task 6: Modernize typing syntax in touched modules

**Files:**
- Modify: `main.py`
- Modify: `kiro/routes_setup.py`
- Modify: nearby touched modules where modernization is low-risk

- [ ] **Step 1: Replace `Optional[T]` with `T | None`**
- [ ] **Step 2: Replace `Union[...]` with `|` syntax**
- [ ] **Step 3: Remove obsolete `typing` imports**
- [ ] **Step 4: Re-run targeted tests for each touched module**

### Task 7: Remove obsolete Python 3.10-specific comments or workarounds

**Files:**
- Modify: `kiro/auth.py`
- Modify: other touched modules only where the comment or branch is clearly tied to 3.10 support

- [ ] **Step 1: Review each 3.10-specific note before editing**
- [ ] **Step 2: Remove or rewrite only when behavior stays identical**
- [ ] **Step 3: Re-run targeted tests covering that code**

## Chunk 4: Verification

### Task 8: Run focused verification

**Files:**
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_main_lifespan.py`
- Test: `tests/unit/test_routes_openai.py`
- Test: `tests/unit/test_routes_anthropic.py`
- Test: `tests/unit/test_webui_routes.py`
- Test: `tests/integration/test_full_flow.py`

- [ ] **Step 1: Run focused pytest commands for changed areas**
- [ ] **Step 2: Fix regressions before broadening**

### Task 9: Run broader verification and dependency audit

**Files:**
- Test: `requirements-dev.txt`
- Test: broad pytest selection

- [ ] **Step 1: Run `python -m pip_audit -r requirements-dev.txt`**
- [ ] **Step 2: Run a broader pytest pass**
- [ ] **Step 3: Summarize remaining risk, especially around 3.11-only lockfiles and route behavior**
