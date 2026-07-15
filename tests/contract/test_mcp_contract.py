"""验证 MCP 工具契约先于实现固定下来。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_mcp_只注册本机研究只读工具并排除破坏性能力() -> None:
    """MCP 首个版本只能暴露研究查询能力，发布、回滚、删除和券商能力不得进入白名单。"""

    from stock_agent.mcp.contracts import MCPToolRegistry

    registry = MCPToolRegistry.default()

    assert registry.tool_names == {
        "market.get_status",
        "market.get_quotes",
        "market.get_history",
        "sector.list",
        "sector.get_metrics",
        "sector.get_rotation",
        "custom_sector.get",
        "custom_sector.get_members_at",
        "prediction.get",
        "prediction.list_history",
        "backtest.get",
        "backtest.start_readonly",
        "report.get",
        "report.list",
        "task.get",
        "task.list",
        "task.start_analysis",
        "model.get",
        "model.list",
        "model.get_evaluation",
    }
    assert "model.publish" not in registry.tool_names
    assert "model.rollback" not in registry.tool_names
    assert "data.delete" not in registry.tool_names
    assert "broker.login" not in registry.tool_names
    assert "trade.place_order" not in registry.tool_names


def test_mcp_工具请求拒绝未知字段和越权参数() -> None:
    """工具输入必须是严格版本化对象，不接受 SQL、文件路径、外部地址、凭据或券商字段。"""

    from stock_agent.mcp.contracts import MCPToolRequest

    valid_request = MCPToolRequest(
        contract_version="1.0",
        request_id=uuid4(),
        tool_name="market.get_quotes",
        params={"market": "CN", "symbols": ["600000.SH"]},
    )

    assert valid_request.params["symbols"] == ["600000.SH"]

    for forbidden_params in [
        {"sql": "select * from quotes"},
        {"file_path": "D:/secret/data.duckdb"},
        {"url": "https://example.com/export"},
        {"credential": "token"},
        {"broker_id": "demo-broker"},
    ]:
        with pytest.raises(ValidationError):
            MCPToolRequest(
                contract_version="1.0",
                request_id=uuid4(),
                tool_name="market.get_quotes",
                params=forbidden_params,
            )

    with pytest.raises(ValidationError):
        MCPToolRequest(
            contract_version="1.0",
            request_id=uuid4(),
            tool_name="market.get_quotes",
            params={"market": "CN"},
            unexpected=True,
        )


def test_mcp_分页超时和幂等键边界可检查() -> None:
    """集合查询、历史查询和启动类工具必须显式限制资源并绑定幂等键。"""

    from stock_agent.mcp.contracts import MCPExecutionOptions, MCPPageRequest, MCPToolRequest

    assert MCPPageRequest().page_size == 50
    assert MCPPageRequest(page_size=200).page_size == 200

    with pytest.raises(ValidationError):
        MCPPageRequest(page_size=201)

    with pytest.raises(ValidationError):
        MCPExecutionOptions(timeout_ms=30_001)

    with pytest.raises(ValidationError):
        MCPToolRequest(
            contract_version="1.0",
            request_id=uuid4(),
            tool_name="task.start_analysis",
            params={"market": "CN"},
            options=MCPExecutionOptions(timeout_ms=30_000),
        )

    start_request = MCPToolRequest(
        contract_version="1.0",
        request_id=uuid4(),
        tool_name="task.start_analysis",
        params={"market": "CN"},
        options=MCPExecutionOptions(timeout_ms=30_000, idempotency_key="daily-cn-20260715"),
    )

    assert start_request.options.idempotency_key == "daily-cn-20260715"


def test_mcp_成功结果必须携带工具元数据和数字溯源() -> None:
    """大模型只能引用工具结果中的数字，缺少工具版本、来源或数据版本时必须拒绝。"""

    from stock_agent.contracts.common import Freshness, SourceProvenance
    from stock_agent.mcp.contracts import MCPToolResult

    result = MCPToolResult[dict[str, float]](
        contract_version="1.0",
        tool_name="market.get_quotes",
        tool_version="1.0.0",
        parameter_digest="market=CN;symbols=600000.SH",
        result_id=uuid4(),
        request_id=uuid4(),
        called_at=datetime(2026, 7, 15, 9, 31, tzinfo=UTC),
        generated_at=datetime(2026, 7, 15, 9, 31, tzinfo=UTC),
        data_as_of=datetime(2026, 7, 15, 9, 30, tzinfo=UTC),
        data_version="quote-cn-v1",
        freshness=Freshness(state="NEAR_REALTIME", age_seconds=30),
        provenance=[
            SourceProvenance(
                source_id="sina-http",
                market_time=datetime(2026, 7, 15, 9, 30, tzinfo=UTC),
                collected_at=datetime(2026, 7, 15, 9, 31, tzinfo=UTC),
                data_version="quote-cn-v1",
                artifact_hash="a" * 64,
            )
        ],
        payload={"last": 10.25},
    )

    assert result.tool_name == "market.get_quotes"
    assert result.payload["last"] == 10.25

    with pytest.raises(ValidationError):
        MCPToolResult[dict[str, float]](
            contract_version="1.0",
            tool_name="market.get_quotes",
            tool_version="1.0.0",
            parameter_digest="market=CN",
            result_id=uuid4(),
            request_id=uuid4(),
            called_at=datetime(2026, 7, 15, 9, 31, tzinfo=UTC),
            generated_at=datetime(2026, 7, 15, 9, 31, tzinfo=UTC),
            data_as_of=datetime(2026, 7, 15, 9, 30, tzinfo=UTC),
            data_version="quote-cn-v1",
            freshness=Freshness(state="NEAR_REALTIME", age_seconds=30),
            provenance=[],
            payload={"last": 10.25},
        )


def test_mcp_预测结果额外要求预测版本和模型版本() -> None:
    """预测工具比普通行情工具多一道版本门禁，防止无法回滚或无法追溯的数字进入解释层。"""

    from stock_agent.contracts.common import Freshness, SourceProvenance
    from stock_agent.mcp.contracts import MCPPredictionToolResult

    result = MCPPredictionToolResult[dict[str, float]](
        contract_version="1.0",
        tool_name="prediction.get",
        tool_version="1.0.0",
        parameter_digest="market=CN;symbol=600000.SH;horizon=5d",
        result_id=uuid4(),
        request_id=uuid4(),
        called_at=datetime(2026, 7, 15, 15, 10, tzinfo=UTC),
        generated_at=datetime(2026, 7, 15, 15, 10, tzinfo=UTC),
        data_as_of=datetime(2026, 7, 15, 15, 0, tzinfo=UTC),
        data_version="features-cn-v1",
        freshness=Freshness(state="CLOSED", age_seconds=600),
        provenance=[
            SourceProvenance(
                source_id="local-feature-snapshot",
                market_time=datetime(2026, 7, 15, 15, 0, tzinfo=UTC),
                collected_at=datetime(2026, 7, 15, 15, 5, tzinfo=UTC),
                data_version="features-cn-v1",
                artifact_hash="b" * 64,
            )
        ],
        prediction_version="pred-20260715-0001",
        model_version="baseline-v1",
        payload={"prob_up": 0.4, "prob_flat": 0.35, "prob_down": 0.25},
    )

    assert result.prediction_version == "pred-20260715-0001"
    assert result.model_version == "baseline-v1"

    with pytest.raises(ValidationError):
        MCPPredictionToolResult[dict[str, float]](
            contract_version="1.0",
            tool_name="prediction.get",
            tool_version="1.0.0",
            parameter_digest="market=CN;symbol=600000.SH;horizon=5d",
            result_id=uuid4(),
            request_id=uuid4(),
            called_at=datetime(2026, 7, 15, 15, 10, tzinfo=UTC),
            generated_at=datetime(2026, 7, 15, 15, 10, tzinfo=UTC),
            data_as_of=datetime(2026, 7, 15, 15, 0, tzinfo=UTC),
            data_version="features-cn-v1",
            freshness=Freshness(state="CLOSED", age_seconds=600),
            provenance=[
                SourceProvenance(
                    source_id="local-feature-snapshot",
                    market_time=datetime(2026, 7, 15, 15, 0, tzinfo=UTC),
                    collected_at=datetime(2026, 7, 15, 15, 5, tzinfo=UTC),
                    data_version="features-cn-v1",
                    artifact_hash="b" * 64,
                )
            ],
            prediction_version="",
            model_version="baseline-v1",
            payload={"prob_up": 0.4, "prob_flat": 0.35, "prob_down": 0.25},
        )


def test_mcp_server_只允许_stdio_或受控本机传输() -> None:
    """MCP Server 启动入口不得接受会绕过本机边界的传输类型。"""

    from stock_agent.adapters.mcp.server import MCPServer, MCPServerConfig

    server = MCPServer.create_local_stdio()

    assert server.config.transport == "stdio"
    assert "prediction.get" in server.tool_names

    with pytest.raises(ValueError):
        MCPServerConfig(transport="tcp")
