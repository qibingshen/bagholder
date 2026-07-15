"""验证板块控制器把服务结果映射为安全页面状态。"""

from decimal import Decimal


def test_板块控制器在覆盖率不足时展示不完整状态() -> None:
    """覆盖率不足时页面不允许展示强弱排名。"""

    from stock_agent.desktop.controllers.sector_controller import SectorController

    view = SectorController().build_overview(
        metrics=[],
        ranking_allowed=False,
        error_code="SECTOR_COVERAGE_TOO_LOW",
    )

    assert view.page_state.status == "INCOMPLETE"
    assert view.ranking_allowed is False
    assert view.rows == ()


def test_板块控制器在无成员时展示空状态() -> None:
    """没有有效成员时应显示空状态，而不是展示零值排名。"""

    from stock_agent.desktop.controllers.sector_controller import SectorController

    view = SectorController().build_overview(metrics=[], ranking_allowed=True, error_code=None)

    assert view.page_state.status == "NO_MEMBERS"
    assert view.rows == ()


def test_板块控制器展示轮动指标行() -> None:
    """有效指标应映射为板块页面行，保留趋势强度、轮动分和覆盖率。"""

    from datetime import date

    from stock_agent.desktop.controllers.sector_controller import SectorController
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

    view = SectorController().build_overview(
        metrics=[metrics], ranking_allowed=True, error_code=None
    )

    assert view.page_state.status == "READY"
    assert view.rows[0].rotation_score == Decimal("0.71")
