"""验证 US8 备份恢复验收说明和结果记录。"""

from pathlib import Path


def test_us8_验收说明包含三平台恢复容量和凭据排除() -> None:
    """US8 验收说明必须覆盖跨平台恢复、容量门禁和凭据排除。"""

    path = Path("docs/acceptance/us8-backup-restore.md")

    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "Windows、macOS、Linux" in content
    assert "200 GB" in content
    assert "80%" in content
    assert "凭据" in content
    assert "隔离恢复" in content
    assert "py -3.12 -m pytest" in content


def test_us8_测试结果记录包含备份容量和失败恢复门禁() -> None:
    """US8 测试结果记录必须列出备份、容量和失败恢复测试。"""

    path = Path("docs/acceptance/us8-test-results.md")

    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "tests/contract/test_backup_contract.py" in content
    assert "tests/property/test_storage_budget.py" in content
    assert "tests/failure/test_backup_recovery_failures.py" in content
    assert "9 passed" in content
    assert "凭据排除" in content
    assert "哈希" in content
