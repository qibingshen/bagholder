"""验证板块契约先于实现固定下来。"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError


def test_主要板块必须声明分类市场币种和成员有效期() -> None:
    """板块定义必须能区分行业、概念、地域，并保留跨市场成员有效区间。"""

    from stock_agent.domain.sector import Sector, SectorMember

    sector = Sector(
        sector_id="sector-cn-bank",
        name="银行",
        category="industry",
        market="CN",
        currency="CNY",
        source_id="local-sector-source",
        data_version="sector-v1",
        members=[
            SectorMember(
                security_key="CN:600000.SH",
                valid_from=date(2026, 1, 1),
                valid_to=None,
                weight=Decimal("0.15"),
            )
        ],
    )

    assert sector.category == "industry"
    assert sector.members[0].valid_from == date(2026, 1, 1)

    with pytest.raises(ValidationError):
        Sector(
            sector_id="sector-invalid",
            name="错误板块",
            category="style",
            market="CN",
            currency="CNY",
            source_id="local-sector-source",
            data_version="sector-v1",
            members=[],
        )


def test_板块指标必须包含涨跌活跃度家数趋势强度轮动和覆盖率() -> None:
    """板块总览必须能独立验收涨跌、成交活跃度、上涨下跌家数、趋势强度和轮动。"""

    from stock_agent.domain.sector import SectorMetrics

    metrics = SectorMetrics(
        sector_id="sector-cn-bank",
        as_of=date(2026, 7, 15),
        return_pct=Decimal("1.20"),
        turnover_activity=Decimal("0.82"),
        advancing_count=18,
        declining_count=7,
        trend_strength=Decimal("0.64"),
        rotation_score=Decimal("0.71"),
        coverage_ratio=Decimal("0.95"),
        data_version="sector-metrics-v1",
    )

    assert metrics.coverage_ratio >= Decimal("0.80")
    assert metrics.advancing_count + metrics.declining_count == 25

    with pytest.raises(ValidationError):
        SectorMetrics(
            sector_id="sector-cn-bank",
            as_of=date(2026, 7, 15),
            return_pct=Decimal("1.20"),
            turnover_activity=Decimal("0.82"),
            advancing_count=18,
            declining_count=7,
            trend_strength=Decimal("0.64"),
            rotation_score=Decimal("0.71"),
            coverage_ratio=Decimal("1.10"),
            data_version="sector-metrics-v1",
        )


def test_自定义板块契约要求追加式成员变更历史() -> None:
    """自定义板块不能静默覆盖成员，历史分析必须使用当时有效成员。"""

    from stock_agent.domain.sector import CustomSector, SectorMemberChange

    custom_sector = CustomSector(
        sector_id="custom-watchlist-1",
        name="我的观察池",
        created_at=date(2026, 7, 10),
        archived_at=None,
        changes=[
            SectorMemberChange(
                change_id="chg-1",
                security_key="US:AAPL",
                action="add",
                effective_date=date(2026, 7, 10),
                source="user",
            ),
            SectorMemberChange(
                change_id="chg-2",
                security_key="US:AAPL",
                action="remove",
                effective_date=date(2026, 7, 15),
                source="user",
            ),
        ],
    )

    assert [change.action for change in custom_sector.changes] == ["add", "remove"]

    with pytest.raises(ValidationError):
        SectorMemberChange(
            change_id="chg-3",
            security_key="US:AAPL",
            action="replace",
            effective_date=date(2026, 7, 15),
            source="user",
        )
