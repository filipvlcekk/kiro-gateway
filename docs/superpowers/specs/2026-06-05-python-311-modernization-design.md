# Python 3.11 Modernization Design

**Goal:** Move the project baseline from Python 3.10+ to Python 3.11+, fix the setup-mode regression introduced by WebUI changes, and modernize internal Python code where the result is clearer and lower-maintenance without changing public API behavior.

**Scope:**
- Runtime baseline: Docker, CI, docs, lockfiles, and install flow.
- Behavioral fix: remove startup-time setup mode lock-in that blocks API routes in tests and valid configured runs.
- Internal modernization: update type syntax and small Python 3.11-era cleanup where it improves readability and does not alter endpoint contracts.

**Non-goals:**
- No public API redesign.
- No payload shape changes for OpenAI or Anthropic compatibility layers.
- No broad architectural refactor unrelated to Python 3.11 support or the setup regression.

## Design

### 1. Platform Baseline

The repository currently claims Python 3.10+ while Docker and CI actively test 3.10. The new baseline will be Python 3.11+ everywhere that defines runtime support. The Docker image will move to `python:3.11-slim`, GitHub Actions will test with Python 3.11, and human-facing documentation will be updated to reflect the new support floor.

Dependency lockfiles will also be treated as 3.11-native artifacts. The hashed install flow already introduced will remain, but it will now be aligned with the actual supported interpreter.

### 2. Setup Mode Regression Fix

The current startup flow computes `_SETUP_REQUIRED` at import time from environment-derived configuration. That value is then copied into `app.state.setup_required` before lifespan runs. This locks the application into setup mode too early, which causes the `/v1/*` guard middleware to short-circuit normal auth, validation, and route logic with a 403 response.

The fix is to make setup mode a runtime state decision rather than an import-time permanent flag. Successful account initialization must explicitly clear `app.state.setup_required`. Tests must also stop mutating `PROXY_API_KEY` at module import time, because that contaminates later imports of `main` and `kiro.config`.

### 3. Python 3.11 Modernization

Modernization will be active but bounded. The main pass will target:
- `Optional[T]` to `T | None`
- `Union[A, B]` to `A | B`
- typing imports that become unnecessary after those conversions
- comments or compatibility notes that only exist because of Python 3.10 support constraints

This will be done selectively in touched files and nearby modules where the change is low-risk and improves clarity. Public behavior, validation rules, and serialization formats must remain unchanged.

### 4. Testing Strategy

Testing will be layered:
- targeted config and workflow tests for the hashed dependency flow
- targeted route and lifespan tests for the setup-mode fix
- targeted module tests for modernized code paths
- a broader pytest run after the behavioral fix lands

The setup-mode regression is the highest-risk functional change, so verification effort should focus there first.

## Guardrails

- Keep infrastructure changes and behavior fixes explicit in separate commits or at least logically separated edits.
- Treat code modernization as cleanup, not as license for opportunistic refactoring.
- If a modernization step changes behavior, back it out and solve the readability issue more narrowly.
