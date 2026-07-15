"""验证 Skill 与大模型不能绕过 MCP 数字溯源和运行边界。"""

from datetime import UTC, datetime
from uuid import uuid4


def test_mcp_超时返回安全错误且部分结果不能当完整数字使用() -> None:
    """超时可以返回部分结果标识，但不得让大模型把部分数字解释为完整结论。"""

    from stock_agent.mcp.runtime import MCPRuntime, MCPRuntimePolicy

    runtime = MCPRuntime(policy=MCPRuntimePolicy(default_timeout_ms=1))

    result = runtime.run_query(
        tool_name="market.get_history",
        request_id=uuid4(),
        params={"market": "CN", "symbol": "600000.SH", "simulate_timeout": True},
    )

    assert result.error.code == "TIMEOUT"
    assert result.error.partial_result_id is not None
    assert result.retryable is True
    assert result.usable_for_llm_numbers is False


def test_mcp_资源限额阻断无界历史查询() -> None:
    """MCP 不得执行超过计划上限的无界本地扫描或超大响应。"""

    from stock_agent.mcp.runtime import MCPRuntime, MCPRuntimePolicy

    runtime = MCPRuntime(policy=MCPRuntimePolicy(max_records=200, max_kline_rows=10_000))

    result = runtime.run_query(
        tool_name="market.get_history",
        request_id=uuid4(),
        params={"market": "CN", "symbol": "600000.SH", "limit": 10_001},
    )

    assert result.error.code == "RESOURCE_LIMIT_EXCEEDED"
    assert result.usable_for_llm_numbers is False


def test_mcp_启动类任务必须用幂等键防止重复执行() -> None:
    """同一幂等键只能复用同一任务，不一致参数不得触发第二次后台任务。"""

    from stock_agent.mcp.runtime import MCPRuntime, MCPRuntimePolicy

    runtime = MCPRuntime(policy=MCPRuntimePolicy())
    first = runtime.start_task(
        tool_name="task.start_analysis",
        request_id=uuid4(),
        idempotency_key="daily-cn-20260715",
        params={"market": "CN", "trade_date": "2026-07-15"},
    )
    replay = runtime.start_task(
        tool_name="task.start_analysis",
        request_id=uuid4(),
        idempotency_key="daily-cn-20260715",
        params={"market": "CN", "trade_date": "2026-07-15"},
    )
    conflict = runtime.start_task(
        tool_name="task.start_analysis",
        request_id=uuid4(),
        idempotency_key="daily-cn-20260715",
        params={"market": "US", "trade_date": "2026-07-15"},
    )

    assert replay.task_id == first.task_id
    assert conflict.error.code == "IDEMPOTENCY_CONFLICT"
    assert conflict.started_new_task is False


def test_skill_越权调用未授权工具会被拒绝并审计() -> None:
    """Skill 清单之外的工具调用必须在执行前被拒绝，而不是由工具内部碰运气。"""

    from stock_agent.mcp.skill_policy import SkillToolPolicy

    policy = SkillToolPolicy.for_skill(
        skill_name="预测复盘",
        allowed_tools={"prediction.list_history", "backtest.get", "report.get"},
    )

    decision = policy.authorize_tool_call("model.publish", params={"model_version": "candidate-v1"})

    assert decision.allowed is False
    assert decision.error_code == "PERMISSION_DENIED"
    assert decision.audit_event.reason == "SKILL_TOOL_NOT_ALLOWED"


def test_过期数字不得驱动当前预测或自然语言结论() -> None:
    """过期行情可解释为不可用状态，但不得继续产生当前预测概率。"""

    from stock_agent.application.numeric_provenance_guard import NumericProvenanceGuard

    from stock_agent.contracts.common import Freshness

    guard = NumericProvenanceGuard()

    decision = guard.evaluate_current_prediction_inputs(
        tool_name="prediction.get",
        freshness=Freshness(state="STALE", age_seconds=86_400),
        data_as_of=datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
        requested_at=datetime(2026, 7, 15, 15, 0, tzinfo=UTC),
        fact_refs=["tool://prediction.get/result-1"],
    )

    assert decision.allowed is False
    assert decision.error_code == "STALE_DATA"
    assert decision.safe_message_zh == "数据已过期，不能生成当前预测。"


def test_大模型缺少工具事实引用时必须拒绝补造数字() -> None:
    """自然语言解释中的每个量化数字都必须绑定 MCP 工具结果引用。"""

    from stock_agent.application.numeric_provenance_guard import NumericProvenanceGuard

    guard = NumericProvenanceGuard()

    decision = guard.validate_llm_answer(
        answer_text="该股票未来 5 日上涨概率为 62%，可以重点关注。",
        numeric_claims=[{"value": "62%", "fact_ref": None}],
        available_fact_refs=[],
    )

    assert decision.allowed is False
    assert decision.error_code == "NUMERIC_PROVENANCE_MISSING"
    assert "不能脱离 MCP 工具结果生成量化数字" in decision.safe_message_zh
