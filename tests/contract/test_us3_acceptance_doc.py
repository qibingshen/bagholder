"""验证 US3 MCP 与数字溯源测试结果记录可复核。"""

from pathlib import Path


def test_us3_测试结果记录包含_mcp_权限和数字溯源门禁() -> None:
    """US3 验收记录必须列出指定测试、执行命令、通过结果和禁止补造数字边界。"""

    path = Path("docs/acceptance/us3-mcp-test-results.md")

    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "tests/contract/test_mcp_contract.py" in content
    assert "tests/contract/test_mcp_permissions.py" in content
    assert "tests/failure/test_skill_numeric_provenance.py" in content
    assert "23 passed" in content
    assert "py -3.12 -m pytest -o addopts=''" in content
    assert "不能脱离 MCP 工具结果生成量化数字" in content
    assert "研究参考，不构成投资建议" in content
