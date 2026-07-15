"""自定义板块成员点时查询和历史断裂阻断规则。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

MembershipAction = Literal["add", "remove"]


@dataclass(frozen=True)
class MembershipEvent:
    """自定义板块成员追加式变更事件。"""

    sequence: int
    security_key: str
    action: MembershipAction
    effective_date: date
    source: str


@dataclass(frozen=True)
class MembershipHistoryGap:
    """成员历史不可用区间。"""

    start: date
    end: date
    reason: str


@dataclass
class SectorMembershipTimeline:
    """按时间保存成员增删事件，并支持点时成员查询。"""

    sector_id: str
    _events: list[MembershipEvent] = field(default_factory=list)
    _gaps: list[MembershipHistoryGap] = field(default_factory=list)

    def add_member(self, security_key: str, effective_date: date, source: str) -> MembershipEvent:
        """追加成员加入事件。"""

        return self._append_event(security_key, "add", effective_date, source)

    def remove_member(
        self, security_key: str, effective_date: date, source: str
    ) -> MembershipEvent:
        """追加成员移除事件。"""

        return self._append_event(security_key, "remove", effective_date, source)

    def members_at(self, as_of: date) -> frozenset[str]:
        """返回指定日期当时有效成员，历史断裂时阻断分析。"""

        for gap in self._gaps:
            if gap.start <= as_of <= gap.end:
                raise ValueError("成员历史存在断裂，不能执行历史分析")
        members: set[str] = set()
        for event in sorted(self._events, key=lambda item: (item.effective_date, item.sequence)):
            if event.effective_date > as_of:
                continue
            if event.action == "add":
                members.add(event.security_key)
            else:
                members.discard(event.security_key)
        return frozenset(members)

    def audit_trail(self) -> tuple[MembershipEvent, ...]:
        """返回按追加顺序保存的审计事件。"""

        return tuple(self._events)

    def mark_history_gap(self, start: date, end: date, reason: str) -> MembershipHistoryGap:
        """记录成员历史不可用区间，后续点时查询必须阻断。"""

        if end < start:
            raise ValueError("历史断裂结束日期不得早于开始日期")
        gap = MembershipHistoryGap(start=start, end=end, reason=reason)
        self._gaps.append(gap)
        return gap

    def _append_event(
        self,
        security_key: str,
        action: MembershipAction,
        effective_date: date,
        source: str,
    ) -> MembershipEvent:
        """追加成员事件并生成单调递增序号。"""

        event = MembershipEvent(
            sequence=len(self._events) + 1,
            security_key=security_key,
            action=action,
            effective_date=effective_date,
            source=source,
        )
        self._events.append(event)
        return event
