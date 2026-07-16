"""验证桌面状态矩阵验收记录覆盖关键页面和差异证据。"""

from pathlib import Path


def test_桌面状态矩阵记录关键页面差异和修复证据() -> None:
    """T121 的验收记录必须列出关键页面、状态差异和可复跑证据。"""

    content = Path("docs/acceptance/desktop-state-matrix.md").read_text(encoding="utf-8")

    for required_text in (
        "市场与证券",
        "板块与自定义板块",
        "预测与复盘",
        "报告与任务",
        "模型中心",
        "数据源管理",
        "差异记录",
        "修复证据",
        "研究参考，不构成投资建议",
    ):
        assert required_text in content
