"""TradingAgents-Astock 单次数据或研究请求隔离进程入口。"""

from __future__ import annotations

import copy
import csv
import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any


def _normalize_action(value: object) -> str:
    """只接受可安全映射的结构化交易动作。"""

    text = str(value).strip().upper()
    aliases = {
        "BUY": "BUY",
        "HOLD": "HOLD",
        "SELL": "SELL",
        "买入": "BUY",
        "持有": "HOLD",
        "卖出": "SELL",
    }
    if text not in aliases:
        raise ValueError("TradingAgents 决策不是 BUY、HOLD 或 SELL")
    return aliases[text]


def _parse_market_output(raw: str) -> tuple[str, list[dict[str, object]]]:
    """把 A 股数据供应商的注释 CSV 转换为白名单记录。"""

    source = ""
    csv_lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# Data source:"):
            source = stripped.split(":", maxsplit=1)[1].strip()
            continue
        if stripped.startswith("#"):
            continue
        csv_lines.append(stripped)
    if not source or not csv_lines or not csv_lines[0].startswith("Date,"):
        raise ValueError("行情数据源返回了无法识别的内容")

    records: list[dict[str, object]] = []
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    reader = csv.DictReader(StringIO("\n".join(csv_lines)))
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("行情数据缺少 OHLCV 字段")
    for row in reader:
        try:
            volume_number = Decimal(str(row["Volume"]))
        except (InvalidOperation, TypeError) as error:
            raise ValueError("行情成交量不是有效数值") from error
        if volume_number != volume_number.to_integral_value() or volume_number < 0:
            raise ValueError("行情成交量必须是非负整数")
        records.append(
            {
                "date": str(row["Date"]),
                "open": str(row["Open"]),
                "high": str(row["High"]),
                "low": str(row["Low"]),
                "close": str(row["Close"]),
                "volume": int(volume_number),
            }
        )
    if not records:
        raise ValueError("行情数据为空")
    return source, records


def _fetch_market(payload: dict[str, Any]) -> dict[str, object]:
    """通过 TradingAgents A 股供应商获取真实日线。"""

    from tradingagents.dataflows.a_stock import get_stock_data

    symbol = str(payload["symbol"])
    start_date = str(payload["start_date"])
    end_date = str(payload["end_date"])
    raw = get_stock_data(symbol, start_date, end_date)
    source, records = _parse_market_output(raw)
    return {
        "security_key": str(payload["security_key"]),
        "start_date": start_date,
        "end_date": end_date,
        "as_of": str(payload["as_of"]),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source": source,
        "records": records,
        "schema_version": "market-v1",
    }


def _json_safe(value: object) -> object:
    """递归移除研究状态中的非 JSON 对象。"""

    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_safe(model_dump())
    return str(value)


def _model_config(payload: dict[str, Any]) -> dict[str, Any]:
    """把专用环境变量映射为 TradingAgents 配置。"""

    from tradingagents.default_config import DEFAULT_CONFIG

    api_key = os.getenv("TRADINGAGENTS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MODEL_NOT_CONFIGURED")
    provider = os.getenv("TRADINGAGENTS_LLM_PROVIDER", "openai").strip() or "openai"
    model = os.getenv("TRADINGAGENTS_MODEL", "").strip()
    if not model:
        raise RuntimeError("MODEL_NOT_CONFIGURED")
    if provider == "openai":
        os.environ["OPENAI_API_KEY"] = api_key

    config = copy.deepcopy(DEFAULT_CONFIG)
    supplied = payload.get("model_config_payload", {})
    if isinstance(supplied, dict):
        config.update(supplied)
    config["llm_provider"] = provider
    config["deep_think_llm"] = model
    config["quick_think_llm"] = model
    backend_url = os.getenv("TRADINGAGENTS_BACKEND_URL", "").strip()
    if backend_url:
        config["backend_url"] = backend_url
    return config


def _run_research(payload: dict[str, Any]) -> dict[str, object]:
    """运行固定版本 TradingAgentsGraph 并输出白名单字段。"""

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(debug=False, config=_model_config(payload))
    final_state, decision = graph.propagate(
        str(payload["symbol"]),
        str(payload["analysis_date"]),
    )
    action_source = (
        decision.get("action", decision.get("final_trade_decision"))
        if isinstance(decision, dict)
        else decision
    )
    confidence = (
        decision.get("confidence", "0")
        if isinstance(decision, dict)
        else final_state.get("confidence", "0")
    )
    report_keys = (
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "investment_debate_state",
        "trader_investment_plan",
        "risk_debate_state",
        "final_trade_decision",
    )
    reports = {
        key: _json_safe(final_state[key])
        for key in report_keys
        if key in final_state
    }
    return {
        "action": _normalize_action(action_source),
        "confidence": str(confidence),
        "model_version": "ta-astock-0.3.0-d55820c",
        "as_of": str(payload["as_of"]),
        "risk_flags": list(final_state.get("risk_flags", [])),
        "reports": reports,
    }


def dispatch(request: dict[str, Any]) -> dict[str, object]:
    """只分发显式允许的数据和研究操作。"""

    operation = request.get("operation")
    payload = request.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("请求 payload 必须是对象")
    if operation == "FETCH_MARKET":
        return _fetch_market(payload)
    if operation == "RUN_RESEARCH":
        return _run_research(payload)
    raise ValueError(f"未知操作：{operation}")


def _error_code(error: Exception) -> str:
    """把内部异常映射为不泄露细节的稳定错误码。"""

    if str(error) == "MODEL_NOT_CONFIGURED":
        return "MODEL_NOT_CONFIGURED"
    if isinstance(error, (KeyError, TypeError, ValueError)):
        return "REQUEST_INVALID"
    return "TRADINGAGENTS_REQUEST_FAILED"


def main() -> int:
    """从标准输入读取一条请求并向标准输出写入一条响应。"""

    line = sys.stdin.readline()
    try:
        if not line:
            raise ValueError("缺少请求")
        request = json.loads(line)
        if not isinstance(request, dict):
            raise ValueError("请求必须是对象")
        response: dict[str, object] = {"ok": True, "result": dispatch(request)}
    except Exception as error:
        print(f"TradingAgents request failed: {type(error).__name__}", file=sys.stderr)
        response = {"ok": False, "error_code": _error_code(error)}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
