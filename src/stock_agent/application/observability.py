"""日志、关联标识和审计的应用层边界。"""

from collections.abc import Mapping
from typing import Protocol


def sanitize_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """在日志、审计和工具错误输出前替换敏感字段，防止凭据泄露。"""
    sensitive = {"apikey", "authorization", "secret", "token", "password", "accesstoken"}

    def sanitize_value(value: object) -> object:
        if isinstance(value, Mapping):
            return sanitize_fields(value)
        if isinstance(value, list):
            return [sanitize_value(item) for item in value]
        return value

    return {
        key: "***" if key.replace("_", "").lower() in sensitive else sanitize_value(value)
        for key, value in fields.items()
    }


class StructuredLogger(Protocol):
    """记录已脱敏的结构化事件；具体脱敏行为由后续先行测试约束。"""

    def emit(self, event_name: str, fields: Mapping[str, object]) -> None:
        """写入包含关联标识的结构化事件。"""
