"""报告中心页面状态。"""

from __future__ import annotations

from dataclasses import dataclass, field

_报告状态说明 = {
    "LOADING": "正在加载本地日报快照。",
    "OFFLINE": "当前离线，仅可查看已保存报告。",
    "PARTIAL_SUCCESS": "日报部分完成，请查看缺失范围和降级影响。",
    "RECOVERED": "日报已恢复并重新验证。",
    "READY": "日报可用于研究查看。",
}


@dataclass(frozen=True, slots=True)
class ReportPageState:
    """报告中心状态，避免把部分报告伪装成完整成功。"""

    status: str
    user_message: str = field(init=False)
    can_show_current_report: bool = field(init=False)
    shows_degradation: bool = field(init=False)

    def __post_init__(self) -> None:
        """锁定报告中心降级语义。"""

        if self.status not in _报告状态说明:
            raise ValueError(f"不支持的报告中心状态：{self.status}")
        object.__setattr__(self, "user_message", _报告状态说明[self.status])
        object.__setattr__(self, "can_show_current_report", self.status in {"READY", "RECOVERED"})
        object.__setattr__(self, "shows_degradation", self.status == "PARTIAL_SUCCESS")
