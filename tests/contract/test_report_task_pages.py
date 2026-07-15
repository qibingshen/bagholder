"""验证报告中心和任务中心页面状态。"""


def test_报告中心页面展示加载离线部分成功和恢复状态() -> None:
    """报告中心必须区分加载、离线、部分成功和恢复状态。"""

    from stock_agent.desktop.pages.report_page import ReportPageState

    assert ReportPageState(status="LOADING").user_message.startswith("正在加载")
    assert ReportPageState(status="OFFLINE").can_show_current_report is False
    assert ReportPageState(status="PARTIAL_SUCCESS").shows_degradation is True
    assert ReportPageState(status="RECOVERED").can_show_current_report is True


def test_任务中心页面展示恢复入口和部分成功警告() -> None:
    """任务中心必须在部分成功和可恢复状态显示安全操作入口。"""

    from stock_agent.desktop.pages.task_page import TaskCenterPageState

    partial = TaskCenterPageState(status="PARTIAL_SUCCESS")
    recovered = TaskCenterPageState(status="RECOVERABLE")

    assert partial.show_warning is True
    assert recovered.show_resume_action is True
    assert TaskCenterPageState(status="OFFLINE").show_resume_action is False
