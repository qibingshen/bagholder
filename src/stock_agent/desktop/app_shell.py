"""PySide6 桌面应用最小启动壳。"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from stock_agent.bootstrap.entrypoints import (
    DESKTOP_ENTRY,
    LOCAL_SERVICE_ENTRY,
    MCP_ENTRY,
    TRAINING_ENTRY,
    WORKER_ENTRY,
)

固定风险提示 = "研究参考，不构成投资建议"


def build_main_window() -> QMainWindow:
    """构建可启动的最小主窗口，后续页面在此基础上接入。"""

    window = QMainWindow()
    window.setWindowTitle("本地量化股票分析智能体")
    window.resize(960, 640)

    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setSpacing(16)
    layout.setContentsMargins(32, 32, 32, 32)

    title = QLabel("本地量化股票分析智能体")
    title.setObjectName("titleLabel")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 26px; font-weight: 700;")

    disclaimer = QLabel(固定风险提示)
    disclaimer.setObjectName("disclaimerLabel")
    disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
    disclaimer.setStyleSheet("font-size: 16px; color: #8a5a00;")

    status = QLabel(
        "MVP 状态：历史日线采集、本地存储、特征计算、简单基准预测、"
        "时间序列回测、MCP 查询、AI 解释和每日报告能力已进入本地闭环验证。"
    )
    status.setObjectName("mvpStatusLabel")
    status.setWordWrap(True)
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    modules = QLabel(
        "当前入口：桌面端、local_service、worker、training、mcp。\n"
        "行情、预测、报告和模型治理数字必须来自本地持久化事实与 MCP 工具结果。"
    )
    modules.setObjectName("moduleSummaryLabel")
    modules.setWordWrap(True)
    modules.setAlignment(Qt.AlignmentFlag.AlignCenter)

    for widget in (title, disclaimer, status, modules):
        layout.addWidget(widget)

    description = "\n".join(
        (
            "本地量化股票分析智能体",
            固定风险提示,
            "MVP 状态包含行情、预测、回测、MCP、AI 解释和每日报告。",
            f"进程入口：{DESKTOP_ENTRY}, {LOCAL_SERVICE_ENTRY}, {WORKER_ENTRY}, "
            f"{TRAINING_ENTRY}, {MCP_ENTRY}",
        )
    )
    window.setAccessibleDescription(description)
    window.setCentralWidget(central)
    return window


def run_desktop_app(argv: list[str] | None = None) -> int:
    """启动 PySide6 事件循环。"""

    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    window = build_main_window()
    window.show()
    return app.exec()
