"""数据管理页面状态。"""

from __future__ import annotations

from dataclasses import dataclass, field

_状态说明 = {
    "READY": "数据管理可用。",
    "STORAGE_WARNING": "本地数据容量接近预算上限。",
    "RESTORE_CONFIRM_REQUIRED": "恢复操作需要用户确认后才能原子切换。",
    "DELETE_IMPACT_CONFIRM_REQUIRED": "删除操作需要确认影响范围。",
}


@dataclass(frozen=True, slots=True)
class DataManagementPageState:
    """备份恢复、容量、导入导出和删除影响确认页面状态。"""

    status: str
    user_message: str = field(init=False)
    show_storage_warning: bool = field(init=False)
    requires_user_confirmation: bool = field(init=False)

    def __post_init__(self) -> None:
        """恢复和删除影响操作必须显式要求用户确认。"""

        if self.status not in _状态说明:
            raise ValueError(f"不支持的数据管理页面状态：{self.status}")
        object.__setattr__(self, "user_message", _状态说明[self.status])
        object.__setattr__(self, "show_storage_warning", self.status == "STORAGE_WARNING")
        object.__setattr__(
            self,
            "requires_user_confirmation",
            self.status in {"RESTORE_CONFIRM_REQUIRED", "DELETE_IMPACT_CONFIRM_REQUIRED"},
        )
