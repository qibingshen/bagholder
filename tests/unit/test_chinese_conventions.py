"""验证项目中文规范检查工具。"""

import sys
from pathlib import Path
from subprocess import run


def test_中文项目文本检查接受合规示例(tmp_path: Path) -> None:
    """合规的中文说明、注释和文档字符串不应触发检查失败。"""

    (tmp_path / "说明.md").write_text("# 使用说明\n\n这是中文说明。\n", encoding="utf-8")
    (tmp_path / "sample.py").write_text(
        '"""中文模块说明。"""\n# 解释数据时点约束。\n', encoding="utf-8"
    )

    result = run(
        [sys.executable, "tools/check_chinese_project_text.py", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_中文项目文本检查跳过外部技能目录(tmp_path: Path) -> None:
    """外部 Skill 原文不是项目自编写说明，不应被中文规范检查阻断。"""

    external = tmp_path / ".agents" / "skills" / "external"
    external.mkdir(parents=True)
    (external / "SKILL.md").write_text(
        "# External skill\n\nEnglish source text.\n", encoding="utf-8"
    )

    result = run(
        [sys.executable, "tools/check_chinese_project_text.py", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
