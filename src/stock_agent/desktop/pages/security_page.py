"""定义个股研究页面的本地事实状态模型，不发起网络访问。"""

from __future__ import annotations

from dataclasses import dataclass, field

from stock_agent.application.market_service import MarketStatus
from stock_agent.desktop.pages._recovery import is_trusted_recovery_fact

_状态说明 = {
    "EMPTY": "暂无可显示的本地证券研究事实。",
    "LOADING": "正在加载已选择证券的本地研究事实。",
    "OFFLINE": "当前处于离线状态，无法显示实时数据。",
    "PERMISSION_DENIED": "数据源权限受限，当前证券事实不可读取。",
    "STALE": "本地证券研究事实已过期，不能作为实时数据使用。",
    "CLOSED": "市场已闭市，不能显示实时数据或进行当前预测。",
    "READY": "本地证券研究事实可用。",
    "RECOVERED": "已恢复：本地证券研究事实已重新验证并可用。",
}

_可用状态 = frozenset({"READY", "RECOVERED"})


@dataclass(frozen=True, slots=True)
class SecurityPageState:
    """个股研究页面仅接受脱敏状态或本地研究视图模型。"""

    status: str
    user_message: str = field(init=False)
    shows_realtime: bool = field(init=False)
    current_prediction_allowed: bool = field(init=False)
    is_available: bool = field(init=False)

    @classmethod
    def from_market_status(cls, market_status: MarketStatus | None) -> SecurityPageState:
        """仅从完整且已验证的本地市场事实创建恢复状态。"""

        if not is_trusted_recovery_fact(market_status):
            return cls(status="STALE")
        return cls._from_trusted_recovery_fact()

    @classmethod
    def _from_trusted_recovery_fact(cls) -> SecurityPageState:
        """受控工厂在事实校验完成后才写入恢复标识。"""

        view_state = cls(status="STALE")
        object.__setattr__(view_state, "status", "RECOVERED")
        object.__setattr__(view_state, "user_message", _状态说明["RECOVERED"])
        object.__setattr__(view_state, "is_available", True)
        return view_state

    def __post_init__(self) -> None:
        """锁定降级页面的展示与预测权限，禁止伪装为实时。"""

        status = "STALE" if self.status == "RECOVERED" else self.status
        if status not in _状态说明:
            raise ValueError(f"不支持的证券页面状态：{self.status}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "user_message", _状态说明[status])
        available = status in _可用状态
        object.__setattr__(self, "is_available", available)
        object.__setattr__(self, "shows_realtime", status == "READY")
        object.__setattr__(self, "current_prediction_allowed", status == "READY")

    @property
    def show_realtime_data(self) -> bool:
        """兼容页面渲染层对实时展示开关的既有命名。"""

        return self.shows_realtime

    @property
    def allow_current_prediction(self) -> bool:
        """兼容页面渲染层对当前预测入口开关的既有命名。"""

        return self.current_prediction_allowed
