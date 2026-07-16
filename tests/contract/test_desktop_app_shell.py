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
