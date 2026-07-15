"""板块页面控制器，把服务结果映射为安全展示状态。"""

from __future__ import annotations

from stock_agent.desktop.pages.sector_page import (
    SectorOverviewRow,
    SectorOverviewView,
    SectorPageState,
)
from stock_agent.domain.sector import SectorMetrics


class SectorController:
    """组装板块总览页面状态。"""

    def build_overview(
        self,
        metrics: list[SectorMetrics],
        ranking_allowed: bool,
        error_code: str | None,
    ) -> SectorOverviewView:
        """根据覆盖率、成员和服务错误生成页面视图。"""

        if error_code == "SECTOR_COVERAGE_TOO_LOW":
            return SectorOverviewView(
                page_state=SectorPageState(status="INCOMPLETE"),
                rows=(),
                ranking_allowed=False,
            )
        if not metrics:
            return SectorOverviewView(
                page_state=SectorPageState(status="NO_MEMBERS"),
                rows=(),
                ranking_allowed=False,
            )
        rows = tuple(
            SectorOverviewRow(
                sector_id=item.sector_id,
                name=item.sector_id,
                return_pct=item.return_pct,
                trend_strength=item.trend_strength,
                rotation_score=item.rotation_score,
                coverage_ratio=item.coverage_ratio,
            )
            for item in metrics
        )
        return SectorOverviewView(
            page_state=SectorPageState(status="READY"),
            rows=rows,
            ranking_allowed=ranking_allowed,
        )
