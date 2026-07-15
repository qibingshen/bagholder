"""验证任务中心视图模型。"""


def test_任务视图模型展示重试取消恢复和通知动作() -> None:
    """任务中心必须把可恢复动作明确暴露给桌面端。"""

    from stock_agent.desktop.viewmodels.task_view_model import TaskItemViewModel

    item = TaskItemViewModel(
        task_id="daily-CN-20260715",
        status="partial_success",
        retryable=True,
        cancellable=False,
        resume_from="预测复盘",
        notification_level="warning",
        safe_message_zh="每日任务部分完成。",
    )

    assert item.can_retry is True
    assert item.can_cancel is False
    assert item.can_resume is True
    assert item.notification_level == "warning"


def test_终态成功任务不允许重试取消或恢复() -> None:
    """成功终态只能查看结果，不能重复触发后台任务。"""

    from stock_agent.desktop.viewmodels.task_view_model import TaskItemViewModel

    item = TaskItemViewModel(
        task_id="daily-CN-20260715",
        status="success",
        retryable=True,
        cancellable=True,
        resume_from="报告生成",
        notification_level="info",
        safe_message_zh="每日任务完成。",
    )

    assert item.can_retry is False
    assert item.can_cancel is False
    assert item.can_resume is False
