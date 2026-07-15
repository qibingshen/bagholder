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


def test_us2_测试结果记录包含三类测试和当前结果() -> None:
    """US2 测试结果记录必须列出指定测试文件、执行命令和可复核结论。"""

    path = Path("docs/acceptance/us2-test-results.md")

    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "tests/contract/test_prediction_contract.py" in content
    assert "tests/property/test_prediction_labels.py" in content
    assert "tests/failure/test_prediction_failures.py" in content
    assert "py -3.12 -m pytest -o addopts=''" in content
    assert "通过" in content
    assert "研究参考，不构成投资建议" in content
    assert "未来数据泄漏" in content
    assert "不可变预测快照" in content
