"""验证板块页面展示状态。"""

from decimal import Decimal


def test_板块总览页面展示覆盖率和禁止误导排名标识() -> None:
    """板块页面必须把覆盖率和排名是否可用直接暴露给界面。"""

    from stock_agent.desktop.pages.sector_page import (
        SectorOverviewRow,
        SectorOverviewView,
        SectorPageState,
    )

    view = SectorOverviewView(
        page_state=SectorPageState(status="READY"),
        rows=(
            SectorOverviewRow(
                sector_id="sector-cn-bank",
                name="银行",
                return_pct=Decimal("1.20"),
                trend_strength=Decimal("0.64"),
                rotation_score=Decimal("0.71"),
                coverage_ratio=Decimal("0.95"),
            ),
        ),
        ranking_allowed=True,
    )

    assert view.page_state.can_show_rankings is True
    assert view.rows[0].coverage_ratio == Decimal("0.95")


def test_自定义板块页面展示成员历史只读状态() -> None:
    """自定义板块页面必须能显示追加式成员历史，而不是只显示当前成员。"""

    from stock_agent.desktop.pages.custom_sector_page import (
        CustomSectorHistoryRow,
        CustomSectorView,
    )

    view = CustomSectorView(
        sector_id="custom-1",
        name="观察池",
        current_members=("HK:00700",),
        history_rows=(
            CustomSectorHistoryRow(sequence=1, security_key="US:AAPL", action="add"),
            CustomSectorHistoryRow(sequence=2, security_key="US:AAPL", action="remove"),
        ),
        readonly_history=True,
    )

    assert view.readonly_history is True
    assert [row.action for row in view.history_rows] == ["add", "remove"]
