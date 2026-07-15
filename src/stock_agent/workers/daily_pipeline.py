"""每日行情更新、预测复盘、报告生成和通知工作者。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineStepResult:
    """每日流水线单个步骤结果。"""

    name: str
    status: str
    missing_range: str | None


@dataclass(frozen=True)
class DailyPipelineReport:
    """每日流水线生成的报告摘要。"""

    market: str
    trade_date: str
    status: str
    missing_ranges: tuple[str, ...]
    degradation_impacts: tuple[str, ...]


class DailyPipeline:
    """组合行情更新、预测复盘和报告生成步骤。"""

    def build_report_from_steps(
        self,
        market: str,
        trade_date: str,
        step_results: tuple[PipelineStepResult, ...],
    ) -> DailyPipelineReport:
        """根据步骤结果生成完整或部分成功报告。"""

        missing_ranges = tuple(step.missing_range for step in step_results if step.missing_range)
        status = "partial_success" if missing_ranges else "success"
        impacts = tuple(
            f"{step.name}不可用，相关章节降级展示"
            for step in step_results
            if step.status != "success"
        )
        return DailyPipelineReport(
            market=market,
            trade_date=trade_date,
            status=status,
            missing_ranges=missing_ranges,
            degradation_impacts=impacts,
        )


@dataclass(frozen=True)
class DailyRecoveryDecision:
    """每日任务错误恢复决策。"""

    next_status: str
    retryable: bool
    safe_message_zh: str


class DailyTaskRecoveryPolicy:
    """把数据源错误映射为可恢复任务状态。"""

    def handle_error(self, error_code: str, retry_count: int) -> DailyRecoveryDecision:
        """限频和临时源错误可重试，其他错误进入失败降级。"""

        _ = retry_count
        if error_code == "RATE_LIMITED":
            return DailyRecoveryDecision(
                next_status="retrying",
                retryable=True,
                safe_message_zh="数据源限频，任务将稍后重试。",
            )
        return DailyRecoveryDecision(
            next_status="failed",
            retryable=False,
            safe_message_zh="每日任务失败，请查看缺失范围和降级影响。",
        )


@dataclass
class DailyPipelineProgress:
    """保存每日任务恢复点。"""

    task_id: str
    status: str = "running"
    completed_steps: tuple[str, ...] = field(default_factory=tuple)
    resume_from: str | None = None

    def mark_step_done(self, step_name: str) -> None:
        """记录已完成步骤。"""

        self.completed_steps = (*self.completed_steps, step_name)
        self.resume_from = _next_step_after(step_name)

    def cancel(self, reason: str) -> None:
        """取消任务并保留恢复点。"""

        _ = reason
        self.status = "cancelled"
        if self.resume_from is None:
            self.resume_from = "行情更新"


@dataclass(frozen=True)
class DailyNotification:
    """每日任务通知内容。"""

    level: str
    title: str
    body: str


class DailyNotificationPolicy:
    """根据任务状态生成不误导用户的通知。"""

    def build_notification(
        self, task_status: str, missing_ranges: tuple[str, ...]
    ) -> DailyNotification:
        """部分成功只能生成警告通知。"""

        if task_status == "partial_success":
            return DailyNotification(
                level="warning",
                title="每日任务部分完成",
                body=f"缺失范围：{', '.join(missing_ranges)}",
            )
        return DailyNotification(level="info", title="每日任务完成", body="所有步骤已完成。")


def _next_step_after(step_name: str) -> str:
    """根据已完成步骤计算下一个恢复点。"""

    order = ("行情更新", "预测复盘", "报告生成", "通知")
    try:
        index = order.index(step_name)
    except ValueError:
        return order[0]
    if index + 1 >= len(order):
        return order[-1]
    return order[index + 1]
