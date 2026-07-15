"""验证 US4 板块验收说明可独立复核。"""

from pathlib import Path


def test_us4_板块验收说明包含成员历史和覆盖率门禁() -> None:
    """US4 验收说明必须覆盖自定义板块历史、覆盖率和禁止误导性排名。"""

    path = Path("docs/acceptance/us4-sector-history.md")

    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "成员有效期" in content
    assert "自定义板块" in content
    assert "覆盖率不足" in content
    assert "禁止误导性排名" in content
    assert "py -3.12 -m pytest" in content
    assert "研究参考，不构成投资建议" in content
