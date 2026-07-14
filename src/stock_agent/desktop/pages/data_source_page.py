"""定义数据源授权页面的安全状态模型。"""

from dataclasses import dataclass

from stock_agent.application.data_source_credential_service import (
    CredentialAuthorization,
    DataSourceSelectionRecord,
)


@dataclass(frozen=True, slots=True)
class DataSourcePageState:
    """向桌面端呈现授权结果，摘要不得包含保险库引用或明文凭据。"""

    source_id: str
    access_state: str
    summary: str

    @classmethod
    def from_authorization(cls, authorization: CredentialAuthorization) -> "DataSourcePageState":
        """将授权状态转换为可解释的页面状态，未授权时明确提示数据降级。"""

        if authorization.is_authorized:
            return cls(
                authorization.source_id, "已授权", "已配置可用凭据，数据源可在授权范围内使用。"
            )
        return cls(authorization.source_id, "受限", "未配置可用凭据，相关数据源已降级。")

    @classmethod
    def from_selection_record(cls, selection: DataSourceSelectionRecord) -> "DataSourcePageState":
        """将不含敏感字段的选择记录转换为桌面摘要。"""

        return cls(
            source_id=selection.source_id,
            access_state=selection.access_state,
            summary=f"{selection.degradation_notice} {selection.audit_note}",
        )
