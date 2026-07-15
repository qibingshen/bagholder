"""强制第一阶段仅提供研究、模拟预测和历史验证能力。"""


class ResearchScopeViolation(PermissionError):
    """表示请求越过研究边界，禁止连接券商、下单或执行真实交易。"""


class ResearchScopeGuard:
    """以白名单保护能力注册；未知能力默认拒绝，避免新增入口绕过研究边界。"""

    _allowed_capabilities = frozenset(
        {
            "market.read",
            "sector.read",
            "prediction.simulate",
            "backtest.read",
            "report.read",
            "task.start_analysis",
            "model.read",
        }
    )

    def assert_allowed(self, capability: str) -> str:
        """验证能力属于研究范围，不允许以配置开关临时放开交易能力。"""

        if capability not in self._allowed_capabilities:
            raise ResearchScopeViolation(
                "第一阶段仅支持研究、模拟预测和历史验证，不连接券商或执行真实交易"
            )
        return capability
