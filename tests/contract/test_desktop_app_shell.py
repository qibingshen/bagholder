"""验证 PySide6 桌面启动壳。"""

import json
import os
from datetime import UTC, datetime


def test_桌面主窗口包含研究提示和_mvp_状态() -> None:
    """最小桌面壳必须展示产品标题、研究风险提示和当前 MVP 状态。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from stock_agent.desktop.app_shell import build_main_window

    app = QApplication.instance() or QApplication([])
    window = build_main_window()

    assert app is not None
    assert window.windowTitle() == "本地量化股票分析智能体"
    assert "研究参考，不构成投资建议" in window.accessibleDescription()
    assert "MVP" in window.accessibleDescription()
    assert "行情" in window.accessibleDescription()


def test_桌面主窗口提供五个本地研究功能页() -> None:
    """五个入口必须明确本地事实边界，空数据时不得展示虚构量化数字。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication, QTabWidget

    from stock_agent.desktop.app_shell import build_main_window

    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    tabs = window.findChild(QTabWidget, "researchTabs")

    assert app is not None
    assert tabs is not None
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "市场总览",
        "个股研究",
        "板块分析",
        "预测中心",
        "报告与任务",
    ]
    for page_name in ("market", "security", "sector", "prediction", "report"):
        page = tabs.findChild(type(tabs.widget(0)), f"{page_name}Page")
        assert page is not None
        assert "暂无" in page.accessibleDescription()
        assert "研究参考，不构成投资建议" in page.accessibleDescription()


def test_市场页提供可点击的美股后台刷新入口() -> None:
    """市场页必须提供已接入后台刷新器的多数据源可点击入口。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton

    from stock_agent.desktop.app_shell import build_main_window

    QApplication.instance() or QApplication([])
    window = build_main_window()
    refresh = window.findChild(QPushButton, "refreshUsQuoteButton")
    source = window.findChild(QComboBox, "quoteSourceSelector")
    symbol = window.findChild(QLineEdit, "quoteSymbolInput")

    assert refresh is not None
    assert refresh.isEnabled()
    assert "后台" in refresh.toolTip()
    assert source is not None
    assert [source.itemData(index)[0] for index in range(source.count())] == [
        "finnhub",
        "finnhub",
        "finnhub",
        "sina",
        "sina",
    ]
    assert symbol is not None
    assert symbol.text() == "AAPL"
    assert refresh.text() == "刷新行情"


def test_市场页提供可追溯行情表() -> None:
    """行情展示必须保留来源、时间、新鲜度和版本列。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication, QTableWidget

    from stock_agent.desktop.app_shell import build_main_window

    QApplication.instance() or QApplication([])
    window = build_main_window()
    table = window.findChild(QTableWidget, "marketQuoteTable")

    assert table is not None
    assert [table.horizontalHeaderItem(index).text() for index in range(table.columnCount())] == [
        "证券",
        "价格",
        "来源",
        "市场时间",
        "采集时间",
        "新鲜度",
        "数据版本",
    ]


def test_市场页启动时展示最新本地行情事实(tmp_path) -> None:
    """桌面启动必须恢复已提交快照，不能要求用户先手动刷新才看到已有数据。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication, QTableWidget

    from stock_agent.application.versioning_service import VersioningService
    from stock_agent.desktop.widgets.research_pages import build_research_tabs

    payload = json.dumps(
        {
            "security_id": {
                "market": "US",
                "exchange": "NASDAQ",
                "display_code": "AAPL",
                "currency": "USD",
            },
            "price": 211.5,
            "source_id": "finnhub",
            "market_time": datetime(2026, 7, 15, 20, 0, tzinfo=UTC).isoformat(),
            "collected_at": datetime(2026, 7, 16, 2, 0, tzinfo=UTC).isoformat(),
            "data_version": "version-new",
            "freshness": {"state": "STALE", "age_seconds": 21600},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    VersioningService(tmp_path).commit_bytes(
        dataset="market-data-normalized",
        version_id="version-new-normalized",
        content=payload,
        source_id="finnhub",
    )

    QApplication.instance() or QApplication([])
    tabs = build_research_tabs(local_data_root=tmp_path)
    table = tabs.findChild(QTableWidget, "marketQuoteTable")

    assert table is not None
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "AAPL"
    assert table.item(0, 1).text() == "211.5"
    assert table.item(0, 2).text() == "finnhub"
    assert table.item(0, 6).text() == "version-new"
