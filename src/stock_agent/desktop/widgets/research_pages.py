"""构建五个仅消费本地事实的研究页面。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from stock_agent.adapters.platform.paths import data_root
from stock_agent.desktop.live_quote_refresh import LiveQuoteRefresh
from stock_agent.desktop.local_quote_cache import load_latest_quotes
from stock_agent.desktop.pages.market_page import MarketPageState
from stock_agent.desktop.pages.prediction_page import PredictionPageState
from stock_agent.desktop.pages.sector_page import SectorPageState
from stock_agent.desktop.pages.security_page import SecurityPageState
from stock_agent.desktop.quote_fetcher import fetch_quote
from stock_agent.domain.prediction import FIXED_RESEARCH_DISCLAIMER


@dataclass(frozen=True, slots=True)
class ResearchPageDefinition:
    """描述页面标题、空状态和量化事实边界。"""

    object_name: str
    tab_title: str
    status_message: str
    provenance_message: str


def build_research_tabs(*, local_data_root: Path | None = None) -> QTabWidget:
    """创建可切换的本地研究入口，不发起网络访问或生成量化数字。"""

    tabs = QTabWidget()
    tabs.setObjectName("researchTabs")
    root = local_data_root or data_root()
    for definition in _page_definitions():
        tabs.addTab(_build_page(definition, root), definition.tab_title)
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


def _build_page(definition: ResearchPageDefinition, local_data_root: Path) -> QWidget:
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
    if definition.object_name == "marketPage":
        table = QTableWidget(0, 7)
        table.setObjectName("marketQuoteTable")
        table.setHorizontalHeaderLabels(
            ["证券", "价格", "来源", "市场时间", "采集时间", "新鲜度", "数据版本"]
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(table)
        cached_quotes = load_latest_quotes(local_data_root)
        if cached_quotes:
            _show_cached_quote_facts(status, provenance, table, cached_quotes)
        controls = QHBoxLayout()
        source = QComboBox()
        source.setObjectName("quoteSourceSelector")
        source.addItem("美股 NASDAQ（Finnhub）", ("finnhub", "NASDAQ"))
        source.addItem("美股 NYSE（Finnhub）", ("finnhub", "NYSE"))
        source.addItem("美股 AMEX（Finnhub）", ("finnhub", "AMEX"))
        source.addItem("A 股上交所（新浪）", ("sina", "SSE"))
        source.addItem("A 股深交所（新浪）", ("sina", "SZSE"))
        symbol = QLineEdit("AAPL")
        symbol.setObjectName("quoteSymbolInput")
        symbol.setPlaceholderText("输入证券代码")
        refresh = QPushButton("刷新行情")
        refresh.setObjectName("refreshUsQuoteButton")
        refresh.setToolTip("刷新操作将在后台任务中执行，不阻塞桌面界面。")

        def update_symbol_example() -> None:
            source_id, exchange = source.currentData()
            examples = {"SSE": "600000", "SZSE": "000001"}
            if source_id == "sina":
                symbol.setText(examples[exchange])
            elif symbol.text().isdigit():
                symbol.setText("AAPL")

        def start_refresh() -> None:
            source_id, exchange = source.currentData()
            display_code = symbol.text().strip().upper()
            if not display_code:
                status.setText("证券代码不能为空，未发起行情请求。")
                return
            refresh.setEnabled(False)
            source.setEnabled(False)
            symbol.setEnabled(False)
            status.setText(f"正在后台刷新 {display_code} 的本地行情事实。")
            worker = LiveQuoteRefresh(
                lambda: fetch_quote(
                    source_id=source_id,
                    exchange=exchange,
                    display_code=display_code,
                    root=local_data_root,
                )
            )
            page._live_quote_refresh = worker  # type: ignore[attr-defined]  # 保留线程引用，防止刷新完成前被回收。
            worker.succeeded.connect(
                lambda quote: _show_quote_fact(
                    status, provenance, refresh, source, symbol, table, quote
                )
            )
            worker.failed.connect(
                lambda message: _show_refresh_failure(status, refresh, source, symbol, message)
            )
            worker.start()

        source.currentIndexChanged.connect(update_symbol_example)
        refresh.clicked.connect(start_refresh)
        controls.addWidget(source)
        controls.addWidget(symbol, 1)
        controls.addWidget(refresh)
        layout.addLayout(controls)
    layout.addStretch()
    return page


def _show_quote_fact(
    status: QLabel,
    provenance: QLabel,
    refresh: QPushButton,
    source: QComboBox,
    symbol: QLineEdit,
    table: QTableWidget,
    quote: object,
) -> None:
    """仅显示后台返回的已持久化行情事实与溯源字段。"""

    status.setText(f"已刷新本地行情：{quote.security_id.display_code}，价格 {quote.price}。")
    provenance.setText(
        f"来源：{quote.source_id}；市场时间：{quote.market_time.isoformat()}；"
        f"采集时间：{quote.collected_at.isoformat()}；新鲜度：{quote.freshness.state}；"
        f"数据版本：{quote.data_version}。"
    )
    row = _quote_row(table, quote.security_id.display_code)
    if row == table.rowCount():
        table.insertRow(row)
    values = (
        quote.security_id.display_code,
        str(quote.price),
        quote.source_id,
        quote.market_time.isoformat(),
        quote.collected_at.isoformat(),
        quote.freshness.state,
        quote.data_version,
    )
    for column, value in enumerate(values):
        table.setItem(row, column, QTableWidgetItem(value))
    refresh.setEnabled(True)
    source.setEnabled(True)
    symbol.setEnabled(True)


def _show_cached_quote_facts(
    status: QLabel,
    provenance: QLabel,
    table: QTableWidget,
    quotes: tuple[object, ...],
) -> None:
    """启动时展示每只证券最新的已提交快照，并明确这是本地恢复数据。"""

    table.setRowCount(0)
    for quote in quotes:
        row = table.rowCount()
        table.insertRow(row)
        values = (
            quote.security_id.display_code,
            str(quote.price),
            quote.source_id,
            quote.market_time.isoformat(),
            quote.collected_at.isoformat(),
            quote.freshness.state,
            quote.data_version,
        )
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(value))
    newest = quotes[0]
    status.setText(f"已恢复 {len(quotes)} 只证券的最新本地行情事实。")
    provenance.setText(
        f"最新来源：{newest.source_id}；市场时间：{newest.market_time.isoformat()}；"
        f"采集时间：{newest.collected_at.isoformat()}；新鲜度：{newest.freshness.state}；"
        f"数据版本：{newest.data_version}。"
    )


def _quote_row(table: QTableWidget, display_code: str) -> int:
    """返回已有证券所在行；尚未展示时返回表格末尾。"""

    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.text() == display_code:
            return row
    return table.rowCount()


def _show_refresh_failure(
    status: QLabel,
    refresh: QPushButton,
    source: QComboBox,
    symbol: QLineEdit,
    message: str,
) -> None:
    """失败时明确降级并恢复操作入口。"""

    status.setText(message)
    refresh.setEnabled(True)
    source.setEnabled(True)
    symbol.setEnabled(True)
