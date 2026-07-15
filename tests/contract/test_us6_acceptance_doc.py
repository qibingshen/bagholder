"""验证 US6 回测验收结果记录可复核。"""

from pathlib import Path


def test_us6_测试结果记录包含回测时间序列和不可成交门禁() -> None:
    """US6 结果记录必须列出指定测试和无未来数据泄漏边界。"""

    path = Path("docs/acceptance/us6-backtest-results.md")

    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "tests/contract/test_backtest_contract.py" in content
    assert "tests/property/test_time_series_backtest.py" in content
    assert "tests/failure/test_backtest_trading_constraints.py" in content
    assert "11 passed" in content
    assert "未来数据泄漏" in content
    assert "不可成交" in content
    assert "研究参考，不构成投资建议" in content
