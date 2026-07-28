import importlib.util
import io
import json
import os
from pathlib import Path
from types import ModuleType

import pytest


def _runner() -> ModuleType:
    path = Path(__file__).parents[2] / "integrations" / "tradingagents" / "runner.py"
    spec = importlib.util.spec_from_file_location("tradingagents_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_research_mode_defaults_to_full(monkeypatch) -> None:
    runner = _runner()
    monkeypatch.delenv("TRADINGAGENTS_RESEARCH_MODE", raising=False)

    assert runner._research_mode() == "FULL"


def test_research_mode_accepts_lightweight(monkeypatch) -> None:
    runner = _runner()
    monkeypatch.setenv("TRADINGAGENTS_RESEARCH_MODE", "lightweight")

    assert runner._research_mode() == "LIGHTWEIGHT"


def test_runner_main_redirects_dependency_stdout_to_stderr(monkeypatch, capsys) -> None:
    runner = _runner()
    request_line = '{"operation":"FETCH_MARKET","payload":{}}\n'
    monkeypatch.setattr(runner.sys, "stdin", io.StringIO(request_line))

    def noisy_dispatch(request: dict[str, object]) -> dict[str, object]:
        print("dependency output")
        return {"value": "accepted"}

    monkeypatch.setattr(runner, "dispatch", noisy_dispatch)

    assert runner.main() == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out) == {"ok": True, "result": {"value": "accepted"}}
    assert captured.err == "dependency output\n"


def test_runner_main_redirects_file_descriptor_stdout_to_stderr(monkeypatch, capfd) -> None:
    runner = _runner()
    request_line = '{"operation":"FETCH_MARKET","payload":{}}\n'
    monkeypatch.setattr(runner.sys, "stdin", io.StringIO(request_line))

    def noisy_dispatch(request: dict[str, object]) -> dict[str, object]:
        os.write(1, b"dependency fd output\n")
        return {"value": "accepted"}

    monkeypatch.setattr(runner, "dispatch", noisy_dispatch)

    assert runner.main() == 0
    captured = capfd.readouterr()

    assert json.loads(captured.out) == {"ok": True, "result": {"value": "accepted"}}
    assert captured.err == "dependency fd output\n"


def test_runner_main_flushes_buffered_direct_stdout_before_restoring_fd(monkeypatch, capfd) -> None:
    runner = _runner()
    request_line = '{"operation":"FETCH_MARKET","payload":{}}\n'
    monkeypatch.setattr(runner.sys, "stdin", io.StringIO(request_line))

    class BufferedDirectStdout:
        def __init__(self) -> None:
            self.buffer = ""
            self.flushed = False

        def write(self, value: str) -> int:
            self.buffer += value
            return len(value)

        def flush(self) -> None:
            self.flushed = True

    direct_stdout = BufferedDirectStdout()
    monkeypatch.setattr(runner.sys, "__stdout__", direct_stdout)

    def noisy_dispatch(request: dict[str, object]) -> dict[str, object]:
        direct_stdout.write("buffered dependency output\n")
        return {"value": "accepted"}

    monkeypatch.setattr(runner, "dispatch", noisy_dispatch)

    assert runner.main() == 0
    captured = capfd.readouterr()

    assert json.loads(captured.out) == {"ok": True, "result": {"value": "accepted"}}
    assert direct_stdout.buffer == "buffered dependency output\n"
    assert direct_stdout.flushed is True


def test_runner_main_writes_response_to_saved_stdout_descriptor(monkeypatch, capfd) -> None:
    runner = _runner()
    request_line = '{"operation":"FETCH_MARKET","payload":{}}\n'
    monkeypatch.setattr(runner.sys, "stdin", io.StringIO(request_line))
    original_write = runner.os.write
    response_fds: list[int] = []

    def tracking_write(fd: int, data: bytes) -> int:
        if data.startswith(b'{"ok":'):
            response_fds.append(fd)
        return original_write(fd, data)

    monkeypatch.setattr(runner.os, "write", tracking_write)
    monkeypatch.setattr(runner, "dispatch", lambda request: {"value": "accepted"})

    assert runner.main() == 0
    captured = capfd.readouterr()

    assert json.loads(captured.out) == {"ok": True, "result": {"value": "accepted"}}
    assert response_fds and response_fds[0] != 1


def test_append_stale_risk_flags_preserves_existing_flags() -> None:
    runner = _runner()
    result: dict[str, object] = {"risk_flags": ["估值波动"], "action": "HOLD"}

    returned = runner._append_stale_risk_flags(
        result,
        {"get_industry_comparison", "get_profit_forecast"},
    )

    assert returned is result
    assert returned["risk_flags"] == [
        "估值波动",
        "外部数据过期回退：get_industry_comparison",
        "外部数据过期回退：get_profit_forecast",
    ]
    assert returned["action"] == "HOLD"


def test_run_analyst_returns_report_after_tool_round() -> None:
    runner = _runner()
    runner._tool_runtime = object

    class FakeAnalyst:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, state: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {"messages": ["request tool"], "market_report": ""}
            return {"messages": ["final answer"], "market_report": "market report"}

    class FakeToolNode:
        def _func(
            self,
            state: dict[str, object],
            config: dict[str, object],
            runtime: object,
        ) -> dict[str, object]:
            assert state["messages"] == ["request tool"]
            assert config == {}
            assert runtime is not None
            return {"messages": ["tool result"]}

    state: dict[str, object] = {"messages": []}

    report = runner._run_analyst(
        node=FakeAnalyst(),
        tool_node=FakeToolNode(),
        state=state,
        report_key="market_report",
    )

    assert report == "market report"
    assert state["messages"] == ["request tool", "tool result", "final answer"]


def test_run_analyst_allows_six_tool_rounds_before_report() -> None:
    runner = _runner()
    runner._tool_runtime = object

    class FakeAnalyst:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, state: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            if self.calls < 6:
                return {"messages": [f"request-{self.calls}"], "fundamentals_report": ""}
            return {"messages": ["final"], "fundamentals_report": "fundamentals report"}

    class FakeToolNode:
        def _func(
            self,
            state: dict[str, object],
            config: dict[str, object],
            runtime: object,
        ) -> dict[str, object]:
            return {"messages": ["tool result"]}

    report = runner._run_analyst(
        node=FakeAnalyst(),
        tool_node=FakeToolNode(),
        state={"messages": []},
        report_key="fundamentals_report",
    )

    assert report == "fundamentals report"


def test_run_analyst_returns_tool_data_when_round_limit_is_reached() -> None:
    runner = _runner()
    runner._tool_runtime = object

    class FakeAnalyst:
        def __call__(self, state: dict[str, object]) -> dict[str, object]:
            return {"messages": [], "fundamentals_report": ""}

    class ToolResult:
        content = "财务原始数据"

    class FakeToolNode:
        def _func(
            self,
            state: dict[str, object],
            config: dict[str, object],
            runtime: object,
        ) -> dict[str, object]:
            return {"messages": [ToolResult()]}

    report = runner._run_analyst(
        node=FakeAnalyst(),
        tool_node=FakeToolNode(),
        state={"messages": []},
        report_key="fundamentals_report",
    )

    assert report == "工具轮次受限；以下为已获取的原始工具数据：\n财务原始数据"


def test_invoke_tool_node_supplies_graph_runtime() -> None:
    runner = _runner()
    runner._tool_runtime = object

    class FakeToolNode:
        def _func(
            self,
            state: dict[str, object],
            config: dict[str, object],
            runtime: object,
        ) -> dict[str, object]:
            assert state == {"messages": ["tool request"]}
            assert config == {}
            assert runtime is not None
            return {"messages": ["tool result"]}

    assert runner._invoke_tool_node(FakeToolNode(), ["tool request"]) == {
        "messages": ["tool result"]
    }


def test_lightweight_research_returns_three_reports(monkeypatch) -> None:
    runner = _runner()
    installed: list[bool] = []
    monkeypatch.setattr(runner, "_install_external_data_cache", lambda: installed.append(True))

    class FakePropagator:
        def create_initial_state(self, symbol: str, analysis_date: str) -> dict[str, object]:
            return {"messages": [("human", symbol)], "date": analysis_date}

    class FakeModel:
        def invoke(self, prompt: str) -> object:
            assert "market report" in prompt
            assert "fundamentals report" in prompt
            return type(
                "Response",
                (),
                {
                    "content": json.dumps(
                        {
                            "action": "HOLD",
                            "confidence": "0.72",
                            "risk_flags": ["估值波动"],
                            "risk_report": "risk report",
                        }
                    )
                },
            )()

    class FakeGraph:
        propagator = FakePropagator()
        quick_thinking_llm = FakeModel()
        tool_nodes = {"market": object(), "fundamentals": object()}

    monkeypatch.setattr(
        runner,
        "_build_lightweight_graph",
        lambda payload: FakeGraph(),
        raising=False,
    )
    monkeypatch.setattr(
        runner,
        "_lightweight_analyst_factories",
        lambda: (lambda llm: object(), lambda llm: object()),
        raising=False,
    )
    monkeypatch.setattr(
        runner,
        "_run_analyst",
        lambda **kwargs: "market report"
        if kwargs["report_key"] == "market_report"
        else "fundamentals report",
    )

    result = runner._run_lightweight_research(
        {
            "symbol": "603986",
            "analysis_date": "2026-07-24",
            "as_of": "2026-07-24T08:00:00+00:00",
        }
    )

    assert result["action"] == "HOLD"
    assert result["confidence"] == "0.72"
    assert result["reports"] == {
        "market_report": "market report",
        "fundamentals_report": "fundamentals report",
        "risk_report": "risk report",
    }
    assert installed == [True]


def test_lightweight_research_rejects_unknown_action(monkeypatch) -> None:
    runner = _runner()
    monkeypatch.setattr(runner, "_install_external_data_cache", lambda: None)

    class FakePropagator:
        def create_initial_state(self, symbol: str, analysis_date: str) -> dict[str, object]:
            return {"messages": [("human", symbol)], "date": analysis_date}

    class FakeModel:
        def invoke(self, prompt: str) -> object:
            return type(
                "Response",
                (),
                {
                    "content": json.dumps(
                        {
                            "action": "WATCH",
                            "confidence": "0.50",
                            "risk_flags": [],
                            "risk_report": "risk report",
                        }
                    )
                },
            )()

    class FakeGraph:
        propagator = FakePropagator()
        quick_thinking_llm = FakeModel()
        tool_nodes = {"market": object(), "fundamentals": object()}

    monkeypatch.setattr(
        runner,
        "_build_lightweight_graph",
        lambda payload: FakeGraph(),
        raising=False,
    )
    monkeypatch.setattr(
        runner,
        "_lightweight_analyst_factories",
        lambda: (lambda llm: object(), lambda llm: object()),
        raising=False,
    )
    monkeypatch.setattr(runner, "_run_analyst", lambda **kwargs: "report")

    with pytest.raises(ValueError, match="BUY"):
        runner._run_lightweight_research(
            {
                "symbol": "603986",
                "analysis_date": "2026-07-24",
                "as_of": "2026-07-24T08:00:00+00:00",
            }
        )
