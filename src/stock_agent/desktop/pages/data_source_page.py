"""定义数据源选择页面的安全状态模型。"""

from dataclasses import dataclass

from stock_agent.application.data_source_credential_service import DataSourceSelectionRecord


@dataclass(frozen=True, slots=True)
class DataSourcePageState:
    """桌面端只从脱敏选择记录渲染数据源状态与摘要。"""

    source_id: str
    access_state: str
    summary: str

    @classmethod
    def from_selection_record(cls, selection: DataSourceSelectionRecord) -> "DataSourcePageState":
        """将不含敏感字段的选择记录转换为桌面摘要。"""

        return cls(
            source_id=selection.source_id,
            access_state=selection.access_state,
            summary=f"{selection.degradation_notice} {selection.audit_note}",
        )
