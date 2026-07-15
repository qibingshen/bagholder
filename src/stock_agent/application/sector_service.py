"""板块强弱、覆盖率和跨市场可比性服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from stock_agent.domain.sector import SectorMetrics


@dataclass(frozen=True)
class SectorRankingResult:
    """板块排名结果；覆盖率不足时不得展示排名。"""

    allowed: bool
    rankings: tuple[SectorMetrics, ...]
    error_code: str | None = None


class SectorRankingService:
    """根据覆盖率门槛生成板块强弱排名。"""

    def __init__(self, min_coverage_ratio: Decimal = Decimal("0.80")) -> None:
        """设置最低覆盖率，避免用小样本产生误导性排名。"""

        self._min_coverage_ratio = min_coverage_ratio

    def rank(self, metrics: list[SectorMetrics]) -> SectorRankingResult:
        """按轮动分和涨跌幅排序；覆盖率不足时阻断。"""

        if any(item.coverage_ratio < self._min_coverage_ratio for item in metrics):
            return SectorRankingResult(
                allowed=False,
                rankings=(),
                error_code="SECTOR_COVERAGE_TOO_LOW",
            )
        rankings = tuple(
            sorted(metrics, key=lambda item: (item.rotation_score, item.return_pct), reverse=True)
        )
        return SectorRankingResult(allowed=True, rankings=rankings)


@dataclass(frozen=True)
class SectorComparisonResult:
    """跨市场板块比较结果。"""

    allowed: bool
    error_code: str | None
    safe_message_zh: str


class SectorComparisonService:
    """校验跨市场板块比较是否具备币种和日历对齐条件。"""

    def compare_cross_market(
        self,
        sector_ids: tuple[str, ...],
        as_of: date,
        normalized_currency: str | None,
        aligned_calendar: bool,
    ) -> SectorComparisonResult:
        """跨市场比较必须先统一币种并对齐交易日历。"""

        _ = sector_ids, as_of
        if normalized_currency is None or not aligned_calendar:
            return SectorComparisonResult(
                allowed=False,
                error_code="NOT_COMPARABLE",
                safe_message_zh="跨市场板块比较需要先统一币种并对齐交易日历。",
            )
        return SectorComparisonResult(allowed=True, error_code=None, safe_message_zh="")
