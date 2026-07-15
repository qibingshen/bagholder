"""验证板块分析的失败场景不会产生误导性排名。"""

from datetime import date
from decimal import Decimal

import pytest


def test_成员历史断裂时阻断历史分析() -> None:
    """成员有效区间存在断裂时，不能用不完整成员集合生成历史板块结论。"""

    from stock_agent.domain.sector_membership import SectorMembershipTimeline

    timeline = SectorMembershipTimeline(sector_id="custom-watchlist-1")
    timeline.add_member("CN:600000.SH", effective_date=date(2026, 7, 10), source="user")
    timeline.mark_history_gap(
        start=date(2026, 7, 12), end=date(2026, 7, 14), reason="source outage"
    )

    with pytest.raises(ValueError, match="成员历史存在断裂"):
        timeline.members_at(date(2026, 7, 13))


def test_覆盖率不足时拒绝板块强弱排名() -> None:
    """覆盖率不足会放大样本偏差，因此不得展示强弱排名。"""

    from stock_agent.application.sector_service import SectorRankingService
    from stock_agent.domain.sector import SectorMetrics

    metrics = SectorMetrics(
        sector_id="sector-cn-bank",
        as_of=date(2026, 7, 15),
        return_pct=Decimal("2.50"),
        turnover_activity=Decimal("0.90"),
        advancing_count=3,
        declining_count=1,
        trend_strength=Decimal("0.80"),
        rotation_score=Decimal("0.75"),
        coverage_ratio=Decimal("0.40"),
        data_version="sector-metrics-v1",
    )

    result = SectorRankingService(min_coverage_ratio=Decimal("0.80")).rank([metrics])

    assert result.allowed is False
    assert result.error_code == "SECTOR_COVERAGE_TOO_LOW"
    assert result.rankings == ()


def test_不可比较市场币种时禁止误导性跨市场排名() -> None:
    """跨市场比较必须先处理币种、交易日历和时间点，否则只能返回不可比较。"""

    from stock_agent.application.sector_service import SectorComparisonService

    result = SectorComparisonService().compare_cross_market(
        sector_ids=("sector-cn-bank", "sector-us-bank"),
        as_of=date(2026, 7, 15),
        normalized_currency=None,
        aligned_calendar=False,
    )

    assert result.allowed is False
    assert result.error_code == "NOT_COMPARABLE"
    assert "跨市场" in result.safe_message_zh
