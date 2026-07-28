# Lightweight Analyst Tool-Limit Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve a lightweight research result when an analyst exhausts its bounded tool rounds but has already retrieved usable external data.

**Architecture:** `_run_analyst` remains bounded at eight rounds. On exhaustion it gathers text content from tool messages, prefixes a deterministic degradation note, and returns it as the analyst report; no tool output keeps the existing error.

**Tech Stack:** Python 3.12, pytest, existing runner.

## Global Constraints

- Never increase the 8-round cap during this change.
- The fallback uses only tool results already obtained in the same research request.
- No usable tool text preserves `LIGHTWEIGHT_ANALYST_TOOL_LIMIT`.

---

### Task 1: Return a marked fallback report from existing tool output

**Files:**
- Modify: `integrations/tradingagents/runner.py`
- Modify: `tests/unit/test_tradingagents_runner.py`

**Interfaces:**
- Produces: `_tool_message_report(messages: list[Any]) -> str`.
- Changes: `_run_analyst(...)` returns the marked tool report only after the eighth reportless round.

- [ ] **Step 1: Write failing tests**

```python
def test_run_analyst_returns_tool_data_when_round_limit_is_reached() -> None:
    report = runner._run_analyst(
        node=AlwaysRequestsTool(),
        tool_node=ToolNodeReturning("财务数据"),
        state={"messages": []},
        report_key="fundamentals_report",
    )
    assert report == "工具轮次受限；以下为已获取的原始工具数据：\n财务数据"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_tradingagents_runner.py -q`

Expected: FAIL with `LIGHTWEIGHT_ANALYST_TOOL_LIMIT`.

- [ ] **Step 3: Implement the minimal fallback**

```python
def _tool_message_report(messages: list[Any]) -> str:
    contents = [str(getattr(item, "content", "")).strip() for item in messages]
    text = "\n\n".join(item for item in contents if item)
    return "工具轮次受限；以下为已获取的原始工具数据：\n" + text if text else ""

# At the limit:
fallback = _tool_message_report(messages)
if fallback:
    return fallback
raise RuntimeError("LIGHTWEIGHT_ANALYST_TOOL_LIMIT")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_tradingagents_runner.py -q`

Expected: PASS.

- [ ] **Step 5: Run end-to-end verification**

Run: `pytest -q`, `ruff check .`, `mypy src`, and then `bagholder research run CN:603986.SH --date 2026-07-24 --json`.

Expected: tests and checks pass; formal research returns a persisted decision without orders.
