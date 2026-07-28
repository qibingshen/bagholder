"""TradingAgents-Astock 单次数据或研究请求隔离进程入口。"""

from __future__ import annotations

import copy
import csv
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO, UnsupportedOperation
from pathlib import Path
from typing import Any

_RUNNER_DIRECTORY = Path(__file__).resolve().parent
if str(_RUNNER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_RUNNER_DIRECTORY))

from external_data_cache import (  # noqa: E402
    CachedVendorRouter,
    SqliteExternalDataCacheStore,
    track_cache_usage,
)

_RESEARCH_MODES = {"FULL", "LIGHTWEIGHT"}
_LIGHTWEIGHT_MAX_TOOL_ROUNDS = 8
_CACHE_ROUTER_INSTALLED = False


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


def _research_mode() -> str:
    """读取研究链路模式，默认保留完整 TradingAgents 图。"""

    mode = os.getenv("TRADINGAGENTS_RESEARCH_MODE", "FULL").strip().upper()
    mode = mode or "FULL"
    if mode not in _RESEARCH_MODES:
        raise ValueError("TRADINGAGENTS_RESEARCH_MODE is invalid")
    return mode


def _cache_directory() -> Path:
    """返回 TradingAgents 专用外部数据缓存目录。"""

    configured = os.getenv("TRADINGAGENTS_CACHE_DIR", "").strip()
    root = Path(configured) if configured else Path.home() / ".tradingagents" / "cache"
    return root / "external-data"


def _cache_vendor_version() -> str:
    """读取进入缓存键的供应商版本，防止版本升级混用旧数据。"""

    return os.getenv(
        "TRADINGAGENTS_EXTERNAL_DATA_CACHE_VENDOR_VERSION",
        "tradingagents-astock-0.3.0-d55820c",
    ).strip() or "tradingagents-astock-0.3.0-d55820c"


def _install_external_data_cache() -> None:
    """让完整图和轻量图的公共行情工具共用同一个缓存路由。"""

    global _CACHE_ROUTER_INSTALLED
    if _CACHE_ROUTER_INSTALLED:
        return
    backend = os.getenv("TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND", "sqlite").strip().lower()
    if backend not in {"", "sqlite"}:
        raise ValueError("TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND is invalid")
    from tradingagents.agents.utils import (
        core_stock_tools,
        fundamental_data_tools,
        signal_data_tools,
        technical_indicators_tools,
    )
    from tradingagents.dataflows.interface import route_to_vendor

    router = CachedVendorRouter(
        upstream=route_to_vendor,
        store=SqliteExternalDataCacheStore(_cache_directory() / "cache.sqlite3"),
        vendor_version=_cache_vendor_version(),
    )
    for module in (
        core_stock_tools,
        fundamental_data_tools,
        signal_data_tools,
        technical_indicators_tools,
    ):
        module.route_to_vendor = router
    _CACHE_ROUTER_INSTALLED = True


def _append_stale_risk_flags(
    result: dict[str, object],
    stale_tool_names: set[str],
) -> dict[str, object]:
    """将已回退的过期数据明确传递给风险结论，不改动决策字段。"""

    raw_flags = result.get("risk_flags", [])
    flags = list(raw_flags) if isinstance(raw_flags, list) else []
    existing = {str(item) for item in flags}
    for tool_name in sorted(stale_tool_names):
        flag = f"外部数据过期回退：{tool_name}"
        if flag not in existing:
            flags.append(flag)
            existing.add(flag)
    result["risk_flags"] = flags
    return result


def _run_analyst(
    *,
    node: Any,
    tool_node: Any,
    state: dict[str, Any],
    report_key: str,
) -> str:
    """在受限轮次内驱动一个带工具的 TradingAgents 分析师。"""

    messages = state.get("messages")
    if not isinstance(messages, list):
        raise ValueError("LIGHTWEIGHT_ANALYST_STATE_INVALID")
    for _ in range(_LIGHTWEIGHT_MAX_TOOL_ROUNDS):
        update = node(state)
        if not isinstance(update, dict):
            raise ValueError("LIGHTWEIGHT_ANALYST_UPDATE_INVALID")
        node_messages = update.get("messages", [])
        if not isinstance(node_messages, list):
            raise ValueError("LIGHTWEIGHT_ANALYST_UPDATE_INVALID")
        messages.extend(node_messages)
        report = str(update.get(report_key, "")).strip()
        if report:
            return report
        tool_update = _invoke_tool_node(tool_node, messages)
        if not isinstance(tool_update, dict):
            raise ValueError("LIGHTWEIGHT_ANALYST_TOOL_INVALID")
        tool_messages = tool_update.get("messages", [])
        if not isinstance(tool_messages, list):
            raise ValueError("LIGHTWEIGHT_ANALYST_TOOL_INVALID")
        messages.extend(tool_messages)
    fallback_report = _tool_message_report(messages)
    if fallback_report:
        return fallback_report
    raise RuntimeError("LIGHTWEIGHT_ANALYST_TOOL_LIMIT")


def _tool_message_report(messages: list[Any]) -> str:
    """在受控轮次耗尽时保留已获取工具数据，供风险模型继续收敛。"""

    contents: list[str] = []
    for message in messages:
        content = getattr(message, "content", "")
        text = content.strip() if isinstance(content, str) else ""
        if text and text not in contents:
            contents.append(text)
    if not contents:
        return ""
    return "工具轮次受限；以下为已获取的原始工具数据：\n" + "\n\n".join(contents)


def _invoke_tool_node(tool_node: Any, messages: list[Any]) -> dict[str, Any]:
    """在图外驱动 ToolNode 时补齐 LangGraph 所需的运行时对象。"""

    result = tool_node._func({"messages": messages}, {}, _tool_runtime())
    if not isinstance(result, dict):
        raise ValueError("LIGHTWEIGHT_ANALYST_TOOL_INVALID")
    return result


def _tool_runtime() -> Any:
    """延迟加载仅存在于 TradingAgents 隔离环境的运行时类型。"""

    from langgraph.runtime import Runtime

    return Runtime()


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


def _run_full_research(payload: dict[str, Any]) -> dict[str, object]:
    """运行固定版本 TradingAgentsGraph 并输出白名单字段。"""

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    _install_external_data_cache()
    with track_cache_usage() as tracker:
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
        result: dict[str, object] = {
            "action": _normalize_action(action_source),
            "confidence": str(confidence),
            "model_version": "ta-astock-0.3.0-d55820c",
            "as_of": str(payload["as_of"]),
            "risk_flags": list(final_state.get("risk_flags", [])),
            "reports": reports,
        }
    return _append_stale_risk_flags(result, tracker.stale_tool_names)


def _build_lightweight_graph(payload: dict[str, Any]) -> Any:
    """构造仅供轻量分析师复用模型和工具节点的图实例。"""

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    return TradingAgentsGraph(
        selected_analysts=["market", "fundamentals"],
        debug=False,
        config=_model_config(payload),
    )


def _lightweight_analyst_factories() -> tuple[Any, Any]:
    """延迟导入分析师工厂，使主环境单元测试无需安装隔离依赖。"""

    from tradingagents.agents.analysts.fundamentals_analyst import (
        create_fundamentals_analyst,
    )
    from tradingagents.agents.analysts.market_analyst import create_market_analyst

    return create_market_analyst, create_fundamentals_analyst


def _risk_conclusion(
    *,
    llm: Any,
    market_report: str,
    fundamentals_report: str,
) -> dict[str, object]:
    """将两份研究报告收敛为一次结构化风险结论。"""

    prompt = f"""你是 A 股风险分析师。只基于下列两份报告，输出一个 JSON 对象，
不得输出 Markdown、解释或额外字段。JSON 必须具有 action、confidence、risk_flags、risk_report：
- action 只能为 BUY、HOLD 或 SELL；
- confidence 是 0 到 1 之间的数字；
- risk_flags 是字符串数组；
- risk_report 是中文风险结论。

行情报告：
{market_report}

基本面报告：
{fundamentals_report}
"""
    response = llm.invoke(prompt)
    raw = getattr(response, "content", "")
    if not isinstance(raw, str):
        raise ValueError("LIGHTWEIGHT_RISK_RESPONSE_INVALID")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("LIGHTWEIGHT_RISK_RESPONSE_INVALID") from error
    if not isinstance(result, dict):
        raise ValueError("LIGHTWEIGHT_RISK_RESPONSE_INVALID")
    action = _normalize_action(result.get("action"))
    try:
        confidence = Decimal(str(result.get("confidence")))
    except (InvalidOperation, TypeError) as error:
        raise ValueError("LIGHTWEIGHT_RISK_CONFIDENCE_INVALID") from error
    if not confidence.is_finite() or not Decimal("0") <= confidence <= Decimal("1"):
        raise ValueError("LIGHTWEIGHT_RISK_CONFIDENCE_INVALID")
    raw_flags = result.get("risk_flags")
    if not isinstance(raw_flags, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_flags
    ):
        raise ValueError("LIGHTWEIGHT_RISK_FLAGS_INVALID")
    risk_report = result.get("risk_report")
    if not isinstance(risk_report, str) or not risk_report.strip():
        raise ValueError("LIGHTWEIGHT_RISK_REPORT_INVALID")
    return {
        "action": action,
        "confidence": str(confidence),
        "risk_flags": [item.strip() for item in raw_flags],
        "risk_report": risk_report.strip(),
    }


def _run_lightweight_research(payload: dict[str, Any]) -> dict[str, object]:
    """按行情、基本面、风险结论三段执行研究。"""

    symbol = str(payload["symbol"])
    analysis_date = str(payload["analysis_date"])
    _install_external_data_cache()
    with track_cache_usage() as tracker:
        graph = _build_lightweight_graph(payload)
        create_market_analyst, create_fundamentals_analyst = _lightweight_analyst_factories()
        state = graph.propagator.create_initial_state(symbol, analysis_date)
        market_report = _run_analyst(
            node=create_market_analyst(graph.quick_thinking_llm),
            tool_node=graph.tool_nodes["market"],
            state=state,
            report_key="market_report",
        )
        state["messages"] = [("human", symbol)]
        fundamentals_report = _run_analyst(
            node=create_fundamentals_analyst(graph.quick_thinking_llm),
            tool_node=graph.tool_nodes["fundamentals"],
            state=state,
            report_key="fundamentals_report",
        )
        risk = _risk_conclusion(
            llm=graph.quick_thinking_llm,
            market_report=market_report,
            fundamentals_report=fundamentals_report,
        )
        result: dict[str, object] = {
            "action": risk["action"],
            "confidence": risk["confidence"],
            "model_version": "ta-astock-lightweight-0.1.0",
            "as_of": str(payload["as_of"]),
            "risk_flags": risk["risk_flags"],
            "reports": {
                "market_report": market_report,
                "fundamentals_report": fundamentals_report,
                "risk_report": risk["risk_report"],
            },
        }
    return _append_stale_risk_flags(result, tracker.stale_tool_names)


def _run_research(payload: dict[str, Any]) -> dict[str, object]:
    """根据配置选择完整或轻量研究链路。"""

    if _research_mode() == "LIGHTWEIGHT":
        return _run_lightweight_research(payload)
    return _run_full_research(payload)


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


@contextmanager
def _redirect_dependency_stdout_to_stderr() -> Iterator[int | None]:
    """隔离依赖直接写入文件描述符 1 的诊断输出。"""

    try:
        stderr_fd = sys.stderr.fileno()
    except (OSError, UnsupportedOperation):
        yield None
        return
    saved_stdout = os.dup(1)
    try:
        os.dup2(stderr_fd, 1)
        yield saved_stdout
    finally:
        try:
            for stream in (sys.stdout, sys.__stdout__):
                if stream is not None:
                    stream.flush()
        finally:
            os.close(saved_stdout)


def _write_response(response_stdout_fd: int | None, response: dict[str, object]) -> None:
    """只通过保留的原始标准输出描述符写入最终 JSON 响应。"""

    payload = (json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    if response_stdout_fd is None:
        sys.stdout.write(payload.decode("utf-8"))
        sys.stdout.flush()
        return
    offset = 0
    while offset < len(payload):
        written = os.write(response_stdout_fd, payload[offset:])
        if written <= 0:
            raise OSError("TradingAgents response write failed")
        offset += written


def main() -> int:
    """从标准输入读取一条请求并向标准输出写入一条响应。"""

    with _redirect_dependency_stdout_to_stderr() as response_stdout_fd:
        line = sys.stdin.readline()
        try:
            if not line:
                raise ValueError("缺少请求")
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("请求必须是对象")
            with redirect_stdout(sys.stderr):
                result = dispatch(request)
            response: dict[str, object] = {"ok": True, "result": result}
        except Exception as error:
            print(f"TradingAgents request failed: {type(error).__name__}", file=sys.stderr)
            response = {"ok": False, "error_code": _error_code(error)}
        _write_response(response_stdout_fd, response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
