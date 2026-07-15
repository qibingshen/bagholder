"""验证审计追加性、日志脱敏和量化数字的工具溯源基础。"""

from uuid import uuid4


def test_审计事件追加保存并关联数字工具溯源(tmp_path) -> None:
    """审计记录必须脱敏且不能覆盖既有事件，数字结果必须指向工具与数据版本。"""

    from stock_agent.application.audit_service import AuditService

    service = AuditService(tmp_path / "audit.duckdb")
    correlation_id = uuid4()
    service.append(
        "credential_configured", {"api_key": "never-log", "source_id": "licensed"}, correlation_id
    )
    service.record_numeric_provenance(
        "result-001", "market.get_history", "daily-cn-v1", ["artifact-001"], correlation_id
    )

    events = service.list_events()
    assert len(events) == 2
    assert events[0].payload["api_key"] == "***"
    assert events[1].payload["tool_name"] == "market.get_history"
    assert events[1].payload["data_version"] == "daily-cn-v1"
