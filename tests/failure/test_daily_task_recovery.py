"""验证每日任务在源失败、限频和中断时安全降级。"""


def test_每日流水线源失败时记录缺失范围并生成部分报告() -> None:
    """数据源失败不得破坏已验证数据，报告必须声明缺失范围和降级影响。"""

    from stock_agent.workers.daily_pipeline import DailyPipeline, PipelineStepResult

    pipeline = DailyPipeline()
    report = pipeline.build_report_from_steps(
        market="CN",
        trade_date="2026-07-15",
        step_results=(
            PipelineStepResult(name="行情更新", status="success", missing_range=None),
            PipelineStepResult(name="板块轮动", status="failed", missing_range="CN:板块轮动"),
        ),
    )

    assert report.status == "partial_success"
    assert report.missing_ranges == ("CN:板块轮动",)
    assert "板块轮动" in report.degradation_impacts[0]


def test_限频错误进入可重试状态且不伪装完成() -> None:
    """限频只能进入重试状态，不能把未完成任务标记为成功。"""

    from stock_agent.workers.daily_pipeline import DailyTaskRecoveryPolicy

    decision = DailyTaskRecoveryPolicy().handle_error(error_code="RATE_LIMITED", retry_count=0)

    assert decision.next_status == "retrying"
    assert decision.retryable is True
    assert decision.safe_message_zh == "数据源限频，任务将稍后重试。"


def test_取消和中断保留恢复点() -> None:
    """取消或进程中断必须保留恢复点，桌面端可继续查看已完成步骤。"""

    from stock_agent.workers.daily_pipeline import DailyPipelineProgress

    progress = DailyPipelineProgress(task_id="daily-CN-20260715")
    progress.mark_step_done("行情更新")
    progress.cancel(reason="用户取消")

    assert progress.status == "cancelled"
    assert progress.resume_from == "预测复盘"
    assert progress.completed_steps == ("行情更新",)


def test_部分报告不能发送完整成功通知() -> None:
    """部分成功报告只能发送降级通知，防止用户误以为数据完整。"""

    from stock_agent.workers.daily_pipeline import DailyNotificationPolicy

    notification = DailyNotificationPolicy().build_notification(
        task_status="partial_success",
        missing_ranges=("US:盘中行情",),
    )

    assert notification.level == "warning"
    assert "部分完成" in notification.title
    assert "US:盘中行情" in notification.body
