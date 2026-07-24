import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_runner() -> ModuleType:
    path = Path(__file__).parents[2] / "integrations" / "tradingagents" / "runner.py"
    spec = importlib.util.spec_from_file_location("bagholder_tradingagents_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_解析真实行情文本并保留数据源() -> None:
    runner = _load_runner()
    raw = """# Stock data for 600519 (A-stock) from 2026-07-24 to 2026-07-24
# Total records: 1
# Data source: sina HTTP (fallback)
# Data retrieved on: 2026-07-25 00:00:00

Date,Open,High,Low,Close,Volume
2026-07-24,1305.0,1309.21,1286.2,1297.41,3569892
"""

    source, records = runner._parse_market_output(raw)

    assert source == "sina HTTP (fallback)"
    assert records == [
        {
            "date": "2026-07-24",
            "open": "1305.0",
            "high": "1309.21",
            "low": "1286.2",
            "close": "1297.41",
            "volume": 3569892,
        }
    ]


def test_行情错误文本不能伪装成空快照() -> None:
    runner = _load_runner()

    with pytest.raises(ValueError, match="行情"):
        runner._parse_market_output("K线数据获取失败：请检查网络连接")


def test_未知操作必须拒绝() -> None:
    runner = _load_runner()

    with pytest.raises(ValueError, match="未知"):
        runner.dispatch({"operation": "DELETE_ALL", "payload": {}})
