# TradingAgents 标准输出协议修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 TradingAgents 运行器在第三方依赖输出诊断文本时仍向主程序返回唯一的 JSON 响应，并安全重试长鑫科技的 PAPER 流程。

**Architecture:** 保持客户端严格的一行 JSON 协议。运行器在分发研究请求时保存原始标准输出描述符，并将进程级文件描述符 1 持续导向标准错误；最终 JSON 只通过保存的描述符写出，确保普通 `print`、直接写入和延迟刷新均不污染响应。

**Tech Stack:** Python 3.12、pytest、Windows PowerShell、TradingAgents 隔离 Python 环境、SQLite PAPER 账本。

## Global Constraints

- 子进程标准输出只允许一行 UTF-8 JSON 响应。
- 不得将客户端改为“取最后一行 JSON”。
- 真实交易保持关闭；只可运行 `PAPER` 模式和本地 `paper-main` 账户。
- 不输出、复制或提交 API 密钥、模型密钥或 `.env` 内容。
- 不提交 Git 变更，除非用户另行明确要求。

---

### Task 1: 覆盖文件描述符级标准输出的回归测试

**Files:**
- Modify: `tests/unit/test_tradingagents_runner.py`
- Modify: `integrations/tradingagents/runner.py`

**Interfaces:**
- Consumes: `main() -> int`、`dispatch(request: dict[str, Any]) -> dict[str, object]`
- Produces: `_redirect_dependency_stdout_to_stderr()` 上下文管理器，分发期间将文件描述符 1 指向标准错误。

- [x] **Step 1: Write the failing test**

```python
def test_runner_main_redirects_file_descriptor_stdout_to_stderr(monkeypatch, capfd) -> None:
    runner = _runner()
    monkeypatch.setattr(runner.sys, "stdin", io.StringIO('{"operation":"FETCH_MARKET","payload":{}}\n'))

    def noisy_dispatch(request: dict[str, object]) -> dict[str, object]:
        os.write(1, b"dependency fd output\\n")
        return {"value": "accepted"}

    monkeypatch.setattr(runner, "dispatch", noisy_dispatch)
    assert runner.main() == 0
    captured = capfd.readouterr()
    assert json.loads(captured.out) == {"ok": True, "result": {"value": "accepted"}}
    assert captured.err == "dependency fd output\\n"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tradingagents_runner.py::test_runner_main_redirects_file_descriptor_stdout_to_stderr -v`

Expected: FAIL because `os.write(1, ...)` bypasses the current Python-level `redirect_stdout` and produces invalid multi-line standard output.

- [x] **Step 3: Write minimal implementation**

```python
@contextmanager
def _redirect_dependency_stdout_to_stderr() -> Iterator[None]:
    saved_stdout = os.dup(sys.stdout.fileno())
    try:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        yield
    finally:
        os.dup2(saved_stdout, sys.stdout.fileno())
        os.close(saved_stdout)
```

Use this context manager around `dispatch(request)` in `main()`. Keep `redirect_stdout(sys.stderr)` nested inside it so both Python-level and file-descriptor-level writers are covered.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tradingagents_runner.py::test_runner_main_redirects_file_descriptor_stdout_to_stderr -v`

Expected: PASS; only the JSON envelope is captured on standard output.

- [x] **Step 5: Run adjacent protocol tests**

Run: `pytest tests/unit/test_tradingagents_runner.py tests/unit/test_tradingagents_client.py -q`

Expected: PASS; the client still rejects an independently malformed multi-line runner response.

### Task 2: 真实研究回归与 PAPER 流程重试

**Files:**
- No source change expected.
- Read: `var/evidence/2026-07-27/CN_688825_SH/`
- Read/Write: `var/platform.db` through the CLI only.

**Interfaces:**
- Consumes: `bagholder research run CN:688825.SH --date 2026-07-27 --start 2026-07-27 --json`
- Produces: a persisted research decision or a stable research rejection; no order is created before `pipeline approve` succeeds.

- [x] **Step 1: Verify the direct research protocol**

Run: `& .\\.venv\\Scripts\\bagholder.exe research run CN:688825.SH --date 2026-07-27 --start 2026-07-27 --json`

Expected: one JSON response; it either contains a structured decision or a business/data error, never `TradingAgentsProtocolError`.

- [x] **Step 2: Generate a PAPER proposal**

Run and retain the returned `run_id` in the current PowerShell session:

```powershell
$runResult = & .\.venv\Scripts\bagholder.exe pipeline run CN:688825.SH --account paper-main --date 2026-07-27 --start 2026-07-27 --mode PAPER --json
$runId = ($runResult | ConvertFrom-Json).run_id
$runResult
```

Expected: a run record. If risk policy rejects the new listing, report its reason and stop; do not bypass the policy.


- [x] **Step 3: Approve only a generated PAPER proposal**

Run the approval in the same PowerShell session using the `run_id` returned in Step 2:

```powershell
& .\.venv\Scripts\bagholder.exe pipeline approve $runId --mode PAPER --json
```

Expected: a local simulated order only when the run has a proposal and passes the PAPER gate. Never pass `--mode LIVE` or `--confirm-live`.

Outcome: the 2026-07-27 run returned `NO_ACTION` because research action was `HOLD`; `proposal_id` was null, so PAPER approval was intentionally not invoked.


- [x] **Step 4: Verify the resulting record**

Run in the same PowerShell session used in Step 3:

```powershell
& .\.venv\Scripts\bagholder.exe pipeline show $runId --json
& .\.venv\Scripts\bagholder.exe paper account show paper-main --json
```

Expected: the run and account ledger agree. If no proposal was allowed, `order_id` remains `null`.

Outcome: run `70dc1fdf-734e-49b9-92c7-5163f5a630cd` had no proposal or order, and `paper-main` retained cash of 1000000.
