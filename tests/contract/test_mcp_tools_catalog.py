"""验证 MCP 只读工具目录和结果包装。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from stock_agent.contracts.common import Freshness, SourceProvenance
from stock_agent.mcp.contracts import MCPToolRequest


def _provenance() -> list[SourceProvenance]:
    return [
        SourceProvenance(
            source_id="local-test-source",
            market_time=datetime(2026, 7, 15, 15, 0, tzinfo=UTC),
            collected_at=datetime(2026, 7, 15, 15, 1, tzinfo=UTC),
            data_version="mcp-test-v1",
            artifact_hash="c" * 64,
        )
    ]


def test_mcp_只读工具目录覆盖六类研究查询() -> None:
    """T062 要求市场、预测、回测、报告、任务和模型查询都能通过 MCP 目录发现。"""

    from stock_agent.adapters.mcp.tools import MCPToolCatalog

    catalog = MCPToolCatalog.default()

    assert catalog.categories == {"market", "prediction", "backtest", "report", "task", "model"}
    assert catalog.get("market.get_quotes").category == "market"
    assert catalog.get("prediction.get").category == "prediction"
    assert catalog.get("backtest.get").category == "backtest"
    assert catalog.get("report.get").category == "report"
    assert catalog.get("task.list").category == "task"
    assert catalog.get("model.get_evaluation").category == "model"

    with pytest.raises(KeyError):
        catalog.get("trade.place_order")


def test_mcp_市场工具把本地服务结果包装为可溯源信封() -> None:
    """工具执行层只包装本地结构化结果，不自行生成行情数字。"""

    from stock_agent.adapters.mcp.tools import MCPToolCatalog, MCPToolExecutionResult

    catalog = MCPToolCatalog.default()
    request = MCPToolRequest(
        contract_version="1.0",
        request_id=uuid4(),
        tool_name="market.get_quotes",
        params={"market": "CN", "symbols": ["600000.SH"]},
    )
    local_result = MCPToolExecutionResult(
        payload={"last": 10.25},
        data_as_of=datetime(2026, 7, 15, 15, 0, tzinfo=UTC),
        data_version="mcp-test-v1",
        freshness=Freshness(state="CLOSED", age_seconds=60),
        provenance=_provenance(),
    )

    result = catalog.invoke(request, lambda _: local_result)

    assert result.tool_name == "market.get_quotes"
    assert result.tool_version == "1.0.0"
    assert result.parameter_digest == "market=CN;symbols=<redacted>"
    assert result.payload["last"] == 10.25
    assert result.provenance[0].source_id == "local-test-source"


def test_mcp_预测工具结果必须包装预测版本和模型版本() -> None:
    """prediction.get 的概率数字必须额外携带预测版本和模型版本。"""

    from stock_agent.adapters.mcp.tools import MCPToolCatalog, MCPToolExecutionResult

    request = MCPToolRequest(
        contract_version="1.0",
        request_id=uuid4(),
        tool_name="prediction.get",
        params={"market": "CN", "symbol": "600000.SH", "horizon": "5d"},
    )
    local_result = MCPToolExecutionResult(
        payload={"prob_up": 0.4, "prob_flat": 0.35, "prob_down": 0.25},
        data_as_of=datetime(2026, 7, 15, 15, 0, tzinfo=UTC),
        data_version="mcp-test-v1",
        freshness=Freshness(state="CLOSED", age_seconds=60),
        provenance=_provenance(),
        prediction_version="pred-20260715-0001",
        model_version="baseline-v1",
    )

    result = MCPToolCatalog.default().invoke(request, lambda _: local_result)

    assert result.prediction_version == "pred-20260715-0001"
    assert result.model_version == "baseline-v1"
