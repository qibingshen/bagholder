"""定义首个版本允许的研究 Skill 与 MCP 工具范围。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillManifest:
    """描述一个 Skill 的用途和允许调用的 MCP 工具。"""

    name: str
    purpose_zh: str
    allowed_tools: frozenset[str]


DEFAULT_SKILL_MANIFESTS: tuple[SkillManifest, ...] = (
    SkillManifest(
        name="每日分析",
        purpose_zh="生成每日市场总结、强弱板块和关注清单。",
        allowed_tools=frozenset(
            {"market.get_status", "market.get_quotes", "report.get", "task.start_analysis"}
        ),
    ),
    SkillManifest(
        name="个股诊断",
        purpose_zh="解释个股行情、指标、预测和风险因素。",
        allowed_tools=frozenset({"market.get_quotes", "market.get_history", "prediction.get"}),
    ),
    SkillManifest(
        name="板块轮动",
        purpose_zh="查询板块强弱、趋势和轮动状态。",
        allowed_tools=frozenset(
            {"sector.list", "sector.get_metrics", "sector.get_rotation", "market.get_status"}
        ),
    ),
    SkillManifest(
        name="预测复盘",
        purpose_zh="查看历史预测、到期结果和基准比较。",
        allowed_tools=frozenset({"prediction.list_history", "backtest.get", "report.get"}),
    ),
    SkillManifest(
        name="模型评估",
        purpose_zh="查看候选模型评估证据，不执行发布。",
        allowed_tools=frozenset({"model.get_evaluation", "backtest.get", "task.start_analysis"}),
    ),
)


def get_skill_manifest(name: str) -> SkillManifest:
    """按名称返回 Skill 清单，未知 Skill 视为配置错误。"""

    for manifest in DEFAULT_SKILL_MANIFESTS:
        if manifest.name == name:
            return manifest
    raise KeyError(name)
