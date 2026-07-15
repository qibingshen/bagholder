"""验证 US5 每日任务与报告验收说明可复核。"""

from pathlib import Path


def test_us5_验收说明包含调度报告恢复和风险提示() -> None:
    """US5 验收说明必须覆盖调度时点、部分报告、恢复流程和固定风险提示。"""

    path = Path("docs/acceptance/us5-daily-reports.md")

    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "A 股、港股、美股" in content
    assert "开盘前、盘中和收盘后" in content
    assert "部分成功" in content
    assert "恢复点" in content
    assert "py -3.12 -m pytest" in content
    assert "研究参考，不构成投资建议" in content
