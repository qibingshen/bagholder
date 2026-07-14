"""定义市场总览页面的本地事实状态模型，不发起网络访问。"""

from __future__ import annotations

from dataclasses import dataclass, field

_状态说明 = {
    "EMPTY": "暂无可显示的本地市场事实。",
    "LOADING": "正在加载已选择范围内的本地市场事实。",
    "OFFLINE": "当前处于离线状态，无法显示实时数据。",
    "PERMISSION_DENIED": "数据源权限受限，当前范围不可读取。",
    "STALE": "本地市场事实已过期，不能作为实时数据使用。",
    "CLOSED": "市场已闭市，不能显示实时数据或进行当前预测。",
    "READY": "本地市场事实可用。",
    "RECOVERED": "已恢复：本地市场事实已重新验证并可用。",
}

_不可实时状态 = frozenset({"OFFLINE", "PERMISSION_DENIED", "STALE", "CLOSED"})
_可用状态 = frozenset({"READY", "RECOVERED"})


@dataclass(frozen=True, slots=True)
class MarketPageState:
    """市场总览仅渲染脱敏状态或已验证的本地市场事实。"""

    status: str
    user_message: str = field(init=False)
    shows_realtime: bool = field(init=False)
    current_prediction_allowed: bool = field(init=False)
    is_available: bool = field(init=False)

    def __post_init__(self) -> None:
        """锁定状态语义，避免将降级状态误标为实时或可预测。"""

        if self.status not in _状态说明:
            raise ValueError(f"不支持的市场页面状态：{self.status}")
        object.__setattr__(self, "user_message", _状态说明[self.status])
        available = self.status in _可用状态
        object.__setattr__(self, "is_available", available)
        object.__setattr__(self, "shows_realtime", self.status == "READY")
        object.__setattr__(self, "current_prediction_allowed", self.status == "READY")

    @property
    def show_realtime_data(self) -> bool:
        """兼容页面渲染层对实时展示开关的既有命名。"""

        return self.shows_realtime

    @property
    def allow_current_prediction(self) -> bool:
        """兼容页面渲染层对当前预测入口开关的既有命名。"""

        return self.current_prediction_allowed
