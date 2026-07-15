"""验证数据管理页面状态。"""


def test_数据管理页面展示备份恢复容量和删除确认状态() -> None:
    """数据管理页必须把容量预警、恢复确认和删除影响明确展示。"""

    from stock_agent.desktop.pages.data_management_page import DataManagementPageState

    warning = DataManagementPageState(status="STORAGE_WARNING")
    restore = DataManagementPageState(status="RESTORE_CONFIRM_REQUIRED")
    delete = DataManagementPageState(status="DELETE_IMPACT_CONFIRM_REQUIRED")

    assert warning.show_storage_warning is True
    assert restore.requires_user_confirmation is True
    assert delete.requires_user_confirmation is True
    assert DataManagementPageState(status="READY").requires_user_confirmation is False
