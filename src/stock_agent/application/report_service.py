"""日报快照生成和版本化存储。"""

from __future__ import annotations

from dataclasses import dataclass, field

from stock_agent.domain.daily_report import DailyReportSnapshot


@dataclass
class DailyReportStore:
    """按报告标识追加保存日报快照版本。"""

    _snapshots: dict[str, list[DailyReportSnapshot]] = field(default_factory=dict)

    def append(self, snapshot: DailyReportSnapshot) -> None:
        """追加保存日报快照，不静默覆盖旧版本。"""

        self._snapshots.setdefault(snapshot.report_id, []).append(snapshot)

    def latest(self, report_id: str) -> DailyReportSnapshot:
        """读取指定报告的最新快照。"""

        return self._snapshots[report_id][-1]

    def versions(self, report_id: str) -> tuple[DailyReportSnapshot, ...]:
        """读取指定报告的全部快照版本。"""

        return tuple(self._snapshots.get(report_id, ()))


class DailyReportService:
    """生成并保存带缺失范围和降级影响的日报快照。"""

    def __init__(self, store: DailyReportStore) -> None:
        """注入版本化日报存储。"""

        self._store = store

    def save_snapshot(self, snapshot: DailyReportSnapshot) -> DailyReportSnapshot:
        """保存日报快照并返回原始快照。"""

        self._store.append(snapshot)
        return snapshot
