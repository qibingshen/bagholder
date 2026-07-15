"""验证模型治理验收说明包含不可绕过的门禁。"""

from pathlib import Path


def test_us7_验收说明覆盖候选模型发布和回滚门禁() -> None:
    """US7 验收说明必须明确候选、影子运行、人工批准、发布失败和回滚边界。"""

    content = Path("docs/acceptance/us7-model-governance.md").read_text(encoding="utf-8")

    for required_text in (
        "候选模型",
        "简单基准",
        "至少 30 个交易日",
        "人工批准",
        "原子发布",
        "回滚",
        "MCP 管理动作",
        "研究参考，不构成投资建议",
    ):
        assert required_text in content
