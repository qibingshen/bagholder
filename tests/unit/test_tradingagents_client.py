import json
import sys
from datetime import date
from pathlib import Path

import pytest


def test_safe_environment_includes_research_mode(monkeypatch) -> None:
    from bagholder.integrations.tradingagents_client import TradingAgentsClient

    monkeypatch.setenv("TRADINGAGENTS_RESEARCH_MODE", "LIGHTWEIGHT")

    assert (
        TradingAgentsClient._safe_environment()["TRADINGAGENTS_RESEARCH_MODE"]
        == "LIGHTWEIGHT"
    )


def test_safe_environment_forwards_external_cache_settings(monkeypatch) -> None:
    from bagholder.integrations.tradingagents_client import TradingAgentsClient

    monkeypatch.setenv("TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND", "sqlite")
    monkeypatch.setenv("TRADINGAGENTS_EXTERNAL_DATA_CACHE_VENDOR_VERSION", "astock-v1")

    environment = TradingAgentsClient._safe_environment()

    assert environment["TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND"] == "sqlite"
    assert environment["TRADINGAGENTS_EXTERNAL_DATA_CACHE_VENDOR_VERSION"] == "astock-v1"


def test_runtime_uses_configured_tradingagents_timeout(monkeypatch) -> None:
    from bagholder.runtime import _tradingagents_timeout_seconds

    monkeypatch.setenv("TRADINGAGENTS_TIMEOUT_SECONDS", "600")

    assert _tradingagents_timeout_seconds() == 600


def _write_runner(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_客户端拒绝标准输出中的额外文本(tmp_path: Path) -> None:
    from bagholder.integrations.tradingagents_client import (
        TradingAgentsClient,
        TradingAgentsProtocolError,
    )

    runner = _write_runner(
        tmp_path / "bad_runner.py",
        "import sys\nsys.stdin.readline()\nprint('debug')\nprint('{}')\n",
    )
    client = TradingAgentsClient(
        python_executable=sys.executable,
        runner_path=runner,
        timeout_seconds=2,
    )

    with pytest.raises(TradingAgentsProtocolError, match="一条 JSON"):
        client.request({"operation": "FETCH_MARKET", "payload": {}})


def test_客户端把结构化行情响应校验为市场快照(tmp_path: Path) -> None:
    from bagholder.contracts.market_data import FetchMarketRequest
    from bagholder.integrations.tradingagents_client import TradingAgentsClient

    result = {
        "ok": True,
        "result": {
            "security_key": "CN:600519.SH",
            "start_date": "2026-07-24",
            "end_date": "2026-07-24",
            "as_of": "2026-07-24",
            "retrieved_at": "2026-07-25T00:00:00+00:00",
            "source": "sina HTTP",
            "records": [
                {
                    "date": "2026-07-24",
                    "open": "1305.00",
                    "high": "1309.21",
                    "low": "1286.20",
                    "close": "1297.41",
                    "volume": 3569892,
                }
            ],
            "schema_version": "market-v1",
        },
    }
    runner = _write_runner(
        tmp_path / "good_runner.py",
        "import json, sys\nsys.stdin.readline()\nprint("
        + repr(json.dumps(result, ensure_ascii=False))
        + ")\n",
    )
    client = TradingAgentsClient(
        python_executable=sys.executable,
        runner_path=runner,
        timeout_seconds=2,
    )

    snapshot = client.fetch_market(
        FetchMarketRequest(
            symbol="600519",
            security_key="CN:600519.SH",
            start_date=date(2026, 7, 24),
            end_date=date(2026, 7, 24),
            as_of=date(2026, 7, 24),
        )
    )

    assert snapshot.records[-1].close.as_tuple().exponent == -2
    assert str(snapshot.records[-1].close) == "1297.41"


def test_客户端忽略非_utf8_错误输出但保留有效响应(tmp_path: Path) -> None:
    from bagholder.integrations.tradingagents_client import TradingAgentsClient

    result = {"ok": True, "result": {"value": "accepted"}}
    runner = _write_runner(
        tmp_path / "non_utf8_stderr_runner.py",
        "import json, sys\n"
        "sys.stdin.readline()\n"
        "sys.stderr.buffer.write('中文警告'.encode('gbk'))\n"
        "print(json.dumps(" + repr(result) + "))\n",
    )
    client = TradingAgentsClient(
        python_executable=sys.executable,
        runner_path=runner,
        timeout_seconds=2,
    )

    assert client.request({"operation": "RUN_RESEARCH", "payload": {}}) == {
        "value": "accepted"
    }


def test_客户端超时返回稳定异常(tmp_path: Path) -> None:
    from bagholder.integrations.tradingagents_client import TradingAgentsClient

    runner = _write_runner(
        tmp_path / "slow_runner.py",
        "import sys, time\nsys.stdin.readline()\ntime.sleep(1)\nprint('{}')\n",
    )
    client = TradingAgentsClient(
        python_executable=sys.executable,
        runner_path=runner,
        timeout_seconds=0.05,
    )

    with pytest.raises(TimeoutError, match="超时"):
        client.request({"operation": "FETCH_MARKET", "payload": {}})
