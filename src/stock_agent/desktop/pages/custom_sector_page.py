"""自定义板块页面展示模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CustomSectorAction = Literal["add", "remove"]


@dataclass(frozen=True, slots=True)
class CustomSectorHistoryRow:
    """自定义板块成员历史行。"""

    sequence: int
    security_key: str
    action: CustomSectorAction


@dataclass(frozen=True, slots=True)
class CustomSectorView:
    """自定义板块视图，当前成员和历史变更同时展示。"""

    sector_id: str
    name: str
    current_members: tuple[str, ...]
    history_rows: tuple[CustomSectorHistoryRow, ...]
    readonly_history: bool

    def __post_init__(self) -> None:
        """成员历史必须只读展示，避免界面静默改写历史。"""

        if not self.readonly_history:
            raise ValueError("自定义板块成员历史必须只读展示")
