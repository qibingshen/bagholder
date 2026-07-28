# Lightweight Research Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in TradingAgents mode that returns market, fundamentals, and one risk conclusion without running the full debate graph.

**Architecture:** `TRADINGAGENTS_RESEARCH_MODE` selects `FULL` or `LIGHTWEIGHT`. The lightweight runner drives the existing market and fundamentals analysts through bounded tool loops, then makes one quick-model call for the risk conclusion. Existing `RUN_RESEARCH` and `ResearchDecision` contracts do not change.

**Tech Stack:** Python 3.12, TradingAgents-Astock, LangChain/LangGraph, pytest, Ruff, Mypy.

## Global Constraints

- `FULL` remains the default; `LIGHTWEIGHT` is case-insensitive.
- Do not place a key in payloads, evidence, SQLite, or logs.
- Lightweight mode cannot access broker or execution components.
- Lightweight reports are `market_report`, `fundamentals_report`, and `risk_report` only.
- Actions remain `BUY`, `HOLD`, or `SELL`; each analyst is limited to four tool rounds.

---

### Task 1: Add mode selection and bounded analyst execution

**Files:**
- Modify: `integrations/tradingagents/runner.py`
- Test: `tests/unit/test_tradingagents_runner.py`

**Interfaces:**
- Produces `_research_mode() -> str`.
- Produces `_run_analyst(*, node: Any, tool_node: Any, state: dict[str, Any], report_key: str) -> str`.

- [ ] **Step 1: Write failing tests**

```python
def test_research_mode_defaults_to_full(monkeypatch) -> None:
    monkeypatch.delenv("TRADINGAGENTS_RESEARCH_MODE", raising=False)
    assert runner._research_mode() == "FULL"

def test_research_mode_accepts_lightweight(monkeypatch) -> None:
    monkeypatch.setenv("TRADINGAGENTS_RESEARCH_MODE", "lightweight")
    assert runner._research_mode() == "LIGHTWEIGHT"

def test_run_analyst_returns_report_after_tool_round() -> None:
    assert runner._run_analyst(...) == "market report"
```

- [ ] **Step 2: Verify RED**

Run `.venv\\Scripts\\python.exe -m pytest tests\\unit\\test_tradingagents_runner.py -q`. It fails because the helpers do not exist.

- [ ] **Step 3: Implement minimum helpers**

```python
def _research_mode() -> str:
    mode = os.getenv("TRADINGAGENTS_RESEARCH_MODE", "FULL").strip().upper() or "FULL"
    if mode not in {"FULL", "LIGHTWEIGHT"}:
        raise ValueError("TRADINGAGENTS_RESEARCH_MODE is invalid")
    return mode

def _run_analyst(*, node: Any, tool_node: Any, state: dict[str, Any], report_key: str) -> str:
    for _ in range(4):
        update = node(state)
        state["messages"].extend(update.get("messages", []))
        report = str(update.get(report_key, ""))
        if report:
            return report
        state["messages"].extend(tool_node.invoke({"messages": state["messages"]})["messages"])
    raise RuntimeError("LIGHTWEIGHT_ANALYST_TOOL_LIMIT")
```

- [ ] **Step 4: Verify GREEN and commit**

Run `.venv\\Scripts\\python.exe -m pytest tests\\unit\\test_tradingagents_runner.py -q`; it passes. Commit with `git add integrations/tradingagents/runner.py tests/unit/test_tradingagents_runner.py` and `git commit -m "feat: add lightweight research helpers"`.

### Task 2: Build the market, fundamentals, and risk path

**Files:**
- Modify: `integrations/tradingagents/runner.py`
- Test: `tests/unit/test_tradingagents_runner.py`

**Interfaces:**
- Produces `_run_lightweight_research(payload: dict[str, Any]) -> dict[str, object]`.
- Consumes `_model_config`, `_run_analyst`, `TradingAgentsGraph`, `create_market_analyst`, and `create_fundamentals_analyst`.

- [ ] **Step 1: Write failing tests**

```python
def test_lightweight_research_returns_three_reports(monkeypatch) -> None:
    result = runner._run_lightweight_research(valid_payload)
    assert result["action"] == "HOLD"
    assert set(result["reports"]) == {"market_report", "fundamentals_report", "risk_report"}

def test_lightweight_research_rejects_unknown_action(monkeypatch) -> None:
    with pytest.raises(ValueError):
        runner._run_lightweight_research(valid_payload)
```

Mock graph construction, analyst factories, tool nodes, and quick-model output so no external call occurs.

- [ ] **Step 2: Verify RED**

Run `.venv\\Scripts\\python.exe -m pytest tests\\unit\\test_tradingagents_runner.py -q`. It fails because `_run_lightweight_research` does not exist.

- [ ] **Step 3: Implement and route**

```python
graph = TradingAgentsGraph(selected_analysts=["market", "fundamentals"], debug=False, config=_model_config(payload))
state = graph.propagator.create_initial_state(symbol, analysis_date)
market_report = _run_analyst(node=create_market_analyst(graph.quick_thinking_llm), tool_node=graph.tool_nodes["market"], state=state, report_key="market_report")
state["messages"] = [("human", symbol)]
fundamentals_report = _run_analyst(node=create_fundamentals_analyst(graph.quick_thinking_llm), tool_node=graph.tool_nodes["fundamentals"], state=state, report_key="fundamentals_report")
```

Make one quick-model call asking for JSON `action`, `confidence`, `risk_flags`, and `risk_report`. Parse with `json.loads`, validate action with `_normalize_action`, validate a finite `Decimal` confidence in `[0, 1]`, and reject blank/non-list risk flags. Move the current implementation to `_run_full_research` and select it only for `FULL`.

- [ ] **Step 4: Verify GREEN and commit**

Run `.venv\\Scripts\\python.exe -m pytest tests\\unit\\test_tradingagents_runner.py -q`; it passes. Commit with `git add integrations/tradingagents/runner.py tests/unit/test_tradingagents_runner.py` and `git commit -m "feat: add lightweight market fundamentals risk research"`.

### Task 3: Propagate configuration and verify end to end

**Files:**
- Modify: `src/bagholder/integrations/tradingagents_client.py`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/unit/test_tradingagents_client.py`

**Interfaces:**
- Passes `TRADINGAGENTS_RESEARCH_MODE` from the parent environment to the runner.

- [ ] **Step 1: Write failing test**

```python
def test_safe_environment_includes_research_mode(monkeypatch) -> None:
    monkeypatch.setenv("TRADINGAGENTS_RESEARCH_MODE", "LIGHTWEIGHT")
    assert TradingAgentsClient._safe_environment()["TRADINGAGENTS_RESEARCH_MODE"] == "LIGHTWEIGHT"
```

- [ ] **Step 2: Verify RED**

Run `.venv\\Scripts\\python.exe -m pytest tests\\unit\\test_tradingagents_client.py -q`. It fails with the missing environment key.

- [ ] **Step 3: Implement and document**

Add the variable to the client allowlist. Add `TRADINGAGENTS_RESEARCH_MODE=FULL` to `.env.example`. Document `FULL` and `LIGHTWEIGHT`, the three reports, and the no-order boundary in `README.md`.

- [ ] **Step 4: Verify full suite and smoke test**

Run `.venv\\Scripts\\python.exe -m pytest -q`, `.venv\\Scripts\\python.exe -m ruff check .`, and `.venv\\Scripts\\python.exe -m mypy src`. Then set `TRADINGAGENTS_RESEARCH_MODE=LIGHTWEIGHT` and run `bagholder research run CN:603986.SH --date 2026-07-24 --evidence-id <existing-market-evidence-id> --json`; it creates only research evidence, never a proposal, order, fill, or live request.

- [ ] **Step 5: Commit**

Commit with `git add src/bagholder/integrations/tradingagents_client.py .env.example README.md tests/unit/test_tradingagents_client.py` and `git commit -m "docs: document lightweight research configuration"`.
