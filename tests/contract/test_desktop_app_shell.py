"""验证 PySide6 桌面启动壳。"""

import os


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
