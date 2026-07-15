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
