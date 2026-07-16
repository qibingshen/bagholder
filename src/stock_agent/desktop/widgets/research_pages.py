"""构建五个仅消费本地事实的研究页面。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from stock_agent.desktop.pages.market_page import MarketPageState
from stock_agent.desktop.pages.prediction_page import PredictionPageState
from stock_agent.desktop.pages.sector_page import SectorPageState
from stock_agent.desktop.pages.security_page import SecurityPageState
from stock_agent.domain.prediction import FIXED_RESEARCH_DISCLAIMER


@dataclass(frozen=True, slots=True)
class ResearchPageDefinition:
    """描述页面标题、空状态和量化事实边界。"""

    object_name: str
    tab_title: str
    status_message: str
    provenance_message: str


def build_research_tabs() -> QTabWidget:
    """创建可切换的本地研究入口，不发起网络访问或生成量化数字。"""

    tabs = QTabWidget()
    tabs.setObjectName("researchTabs")
    for definition in _page_definitions():
        tabs.addTab(_build_page(definition), definition.tab_title)
    return tabs


def _page_definitions() -> tuple[ResearchPageDefinition, ...]:
    """从既有页面状态模型取得空状态，保持展示语义与领域规则一致。"""

    return (
        ResearchPageDefinition(
            object_name="marketPage",
            tab_title="市场总览",
            status_message=MarketPageState(status="EMPTY").user_message,
            provenance_message="行情来源、市场时间、采集时间、新鲜度与数据版本：暂无本地事实。",
        ),
        ResearchPageDefinition(
            object_name="securityPage",
            tab_title="个股研究",
            status_message=SecurityPageState(status="EMPTY").user_message,
            provenance_message="证券代码、K 线、成交量、指标与所属板块：暂无本地事实。",
        ),
        ResearchPageDefinition(
            object_name="sectorPage",
            tab_title="板块分析",
            status_message=SectorPageState(status="EMPTY").user_message,
            provenance_message="板块成员历史、覆盖率、趋势强度与轮动依据：暂无本地事实。",
        ),
        ResearchPageDefinition(
            object_name="predictionPage",
            tab_title="预测中心",
            status_message=PredictionPageState(status="EMPTY").user_message,
            provenance_message="上涨、震荡、下跌概率及置信度、模型版本与风险因素：暂无本地预测快照。",
        ),
        ResearchPageDefinition(
            object_name="reportPage",
            tab_title="报告与任务",
            status_message="暂无本地日报快照或任务记录。",
            provenance_message="每日报告、任务状态、缺失范围与降级影响：暂无本地事实。",
        ),
    )


def _build_page(definition: ResearchPageDefinition) -> QWidget:
    """渲染一个安全空状态，数据接入前不显示任何未证实数字。"""

    page = QWidget()
    page.setObjectName(definition.object_name)
    page.setAccessibleDescription(
        "\n".join(
            (
                definition.tab_title,
                definition.status_message,
                definition.provenance_message,
                FIXED_RESEARCH_DISCLAIMER,
            )
        )
    )

    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)

    heading = QLabel(definition.tab_title)
    heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
    heading.setStyleSheet("font-size: 20px; font-weight: 700;")

    status = QLabel(definition.status_message)
    status.setObjectName(f"{definition.object_name}Status")
    status.setWordWrap(True)

    provenance = QLabel(definition.provenance_message)
    provenance.setObjectName(f"{definition.object_name}Provenance")
    provenance.setWordWrap(True)

    disclaimer = QLabel(FIXED_RESEARCH_DISCLAIMER)
    disclaimer.setObjectName(f"{definition.object_name}Disclaimer")
    disclaimer.setStyleSheet("color: #8a5a00;")

    for widget in (heading, status, provenance, disclaimer):
        layout.addWidget(widget)
    layout.addStretch()
    return page
