# Project Local Model Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load a Git-ignored project-local `.env` safely, preserve explicit system environment variables, and verify a real lightweight 603986 research request.

**Architecture:** A standard-library parser reads only root `.env` lines in `KEY=VALUE` form before the command parser builds the runtime. Existing environment variables take precedence, so deployment and user-level secure configuration remain authoritative. The local file is ignored by Git and is never printed or recorded in tests.

**Tech Stack:** Python 3.12 standard library, pytest, existing TradingAgents isolated runtime.

## Global Constraints

- `.env` is Git-ignored and API keys must never appear in logs, tests, README examples, Git output, or chat responses.
- Only missing process environment variables are populated from the root `.env`.
- The existing `.env.example` remains the committed template.
- The real research check may invoke the configured model and public data providers, but must not create orders or enable live trading.

---

### Task 1: Load project-local environment before runtime construction

**Files:**
- Modify: `src/bagholder/bootstrap.py`
- Modify: `tests/unit/test_bootstrap.py`

**Interfaces:**
- Produces: `_load_project_env(project_root: Path) -> None`, invoked by `main` before `_build_parser()`.

- [ ] **Step 1: Write failing tests**

```python
def test_project_env_populates_missing_values(monkeypatch, tmp_path: Path) -> None:
    from bagholder.bootstrap import _load_project_env
    (tmp_path / ".env").write_text("TRADINGAGENTS_MODEL=local-model\n", encoding="utf-8")
    monkeypatch.delenv("TRADINGAGENTS_MODEL", raising=False)

    _load_project_env(tmp_path)

    assert os.environ["TRADINGAGENTS_MODEL"] == "local-model"

def test_project_env_does_not_override_process_values(monkeypatch, tmp_path: Path) -> None:
    from bagholder.bootstrap import _load_project_env
    (tmp_path / ".env").write_text("TRADINGAGENTS_MODEL=local-model\n", encoding="utf-8")
    monkeypatch.setenv("TRADINGAGENTS_MODEL", "system-model")

    _load_project_env(tmp_path)

    assert os.environ["TRADINGAGENTS_MODEL"] == "system-model"
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/unit/test_bootstrap.py -q`

Expected: FAIL because `_load_project_env` does not exist.

- [ ] **Step 3: Implement the parser and startup hook**

```python
def _load_project_env(project_root: Path) -> None:
    env_file = project_root / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip())
```

Call `_load_project_env(Path.cwd())` at the start of `main`. Do not print file content or values.

- [ ] **Step 4: Run focused test and verify pass**

Run: `pytest tests/unit/test_bootstrap.py -q`

Expected: PASS.

### Task 2: Create secure local settings and run a real research check

**Files:**
- Create: `.env` (ignored local configuration only)

**Interfaces:**
- Consumes: model provider, model name, base URL and API key from `C:/Users/qibingshen/.config/opencode/opencode.jsonc`.
- Produces: local TradingAgents settings for provider, model, key, backend URL, 600-second timeout, LIGHTWEIGHT mode, and SQLite cache.

- [ ] **Step 1: Read source configuration without displaying the API key**

Run a local extraction that reports only provider, model, backend URL and whether a non-empty key exists.

- [ ] **Step 2: Write `.env`**

```dotenv
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_MODEL=<source model name>
TRADINGAGENTS_API_KEY=<source API key>
TRADINGAGENTS_BACKEND_URL=<source base URL>
TRADINGAGENTS_TIMEOUT_SECONDS=600
TRADINGAGENTS_RESEARCH_MODE=LIGHTWEIGHT
TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND=sqlite
```

Retain existing system values when present; the file supplies project-local values for a fresh shell.

- [ ] **Step 3: Verify configuration without printing the key**

Run `bagholder status --json` and assert that the main and TradingAgents environments report ready.

- [ ] **Step 4: Run real lightweight research**

Run `bagholder research run CN:603986.SH --date 2026-07-24 --json` with the local project environment. Confirm a structured `ResearchDecision` is produced, with no order or live-trading action.

- [ ] **Step 5: Run repository regression checks**

Run: `pytest -q`

Expected: all unit and integration tests pass; the optional external market test remains skipped by default.

Run: `ruff check .`

Expected: `All checks passed!`.

Run: `mypy src`

Expected: `Success: no issues found`.
