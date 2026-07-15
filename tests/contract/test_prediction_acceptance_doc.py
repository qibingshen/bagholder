"""验证 US2 预测安全验收说明可检查且包含固定风险提示。"""

from pathlib import Path


def test_us2_预测验收说明包含门禁命令和固定风险提示() -> None:
    """验收文档必须能独立复核预测安全边界，而不是只写完成结论。"""

    path = Path("docs/acceptance/us2-prediction-safety.md")

    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "研究参考，不构成投资建议" in content
    assert "py -3.12 -m pytest" in content
    assert "当前预测阻断" in content
    assert "历史预测快照" in content
    assert "数字溯源" in content
    assert "未来数据" in content
