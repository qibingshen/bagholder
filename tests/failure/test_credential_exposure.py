"""验证凭据不会进入日志、导出、备份或 MCP 结果。"""


def test_结构化日志必须脱敏凭据和授权头() -> None:
    """任何带密钥字段的事件写入前都应替换为固定脱敏标记。"""

    from stock_agent.application.observability import sanitize_fields

    sanitized = sanitize_fields(
        {"source_id": "licensed-source", "api_key": "secret-value", "Authorization": "Bearer token"}
    )

    assert sanitized["source_id"] == "licensed-source"
    assert sanitized["api_key"] == "***"
    assert sanitized["Authorization"] == "***"


def test_驼峰命名的敏感字段同样必须脱敏() -> None:
    """外部工具常用 apiKey 等字段名，不能因命名风格差异泄露密钥。"""

    from stock_agent.application.observability import sanitize_fields

    sanitized = sanitize_fields({"apiKey": "secret-value", "accessToken": "token-value"})

    assert sanitized == {"apiKey": "***", "accessToken": "***"}
