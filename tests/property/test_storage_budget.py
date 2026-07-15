"""验证本地存储容量预算和跨平台路径适配。"""


def test_容量预算超过_200gb_或_80_percent_时触发门禁() -> None:
    """本地数据不得无提示突破规格确认的容量边界。"""

    from stock_agent.application.storage_budget_service import StorageBudgetService

    service = StorageBudgetService(max_bytes=200 * 1024**3, warning_ratio=0.8)

    assert service.evaluate(used_bytes=150 * 1024**3).status == "OK"
    assert service.evaluate(used_bytes=170 * 1024**3).status == "WARNING"
    assert service.evaluate(used_bytes=210 * 1024**3).status == "BLOCKED"


def test_分钟线选择超过上限时拒绝保存计划() -> None:
    """分钟线保存范围必须受控，避免本地磁盘被无界增长耗尽。"""

    from stock_agent.application.storage_budget_service import MinuteRetentionPolicy

    policy = MinuteRetentionPolicy(max_symbols=500, max_days=365)

    assert policy.validate(symbol_count=500, retention_days=365).allowed is True
    assert policy.validate(symbol_count=501, retention_days=365).allowed is False
    assert policy.validate(symbol_count=500, retention_days=366).allowed is False


def test_平台路径适配返回不同系统的数据目录() -> None:
    """Windows、macOS 和 Linux 必须通过集中路径适配处理存储目录差异。"""

    from stock_agent.application.storage_budget_service import PlatformDataDirectory

    assert "AppData" in str(PlatformDataDirectory.for_platform("Windows", "alice"))
    assert "Application Support" in str(PlatformDataDirectory.for_platform("Darwin", "alice"))
    assert ".local" in str(PlatformDataDirectory.for_platform("Linux", "alice"))
