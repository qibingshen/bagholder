"""验证每日调度、报告和任务状态契约先于实现固定下来。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


def test_每日任务契约必须记录市场阶段报告类型和数据版本() -> None:
    """每日任务必须可审计，并能区分开盘前、盘中和收盘后阶段。"""

    from stock_agent.domain.daily_report import DailyTaskContract

    task = DailyTaskContract(
        task_id="daily-CN-20260715-post-close",
        market="CN",
        trade_date="2026-07-15",
        phase="post_close",
        report_type="market_summary",
        status="pending",
        data_version="daily-task-v1",
        scheduled_for=datetime(2026, 7, 15, 15, 30, tzinfo=UTC),
    )

    assert task.phase == "post_close"
    assert task.status == "pending"

    with pytest.raises(ValidationError):
        DailyTaskContract(
            task_id="daily-CN-20260715-invalid",
            market="CN",
            trade_date="2026-07-15",
            phase="overnight",
            report_type="market_summary",
            status="pending",
            data_version="daily-task-v1",
            scheduled_for=datetime(2026, 7, 15, 15, 30, tzinfo=UTC),
        )


def test_日报快照必须包含缺失范围降级影响来源和固定风险提示() -> None:
    """日报不能静默掩盖源失败或缺失范围，必须保留研究风险提示。"""

    from stock_agent.domain.daily_report import DailyReportSnapshot

    snapshot = DailyReportSnapshot(
        report_id="report-CN-20260715",
        market="CN",
        trade_date="2026-07-15",
        generated_at=datetime(2026, 7, 15, 16, 0, tzinfo=UTC),
        data_version="daily-report-v1",
        source_ids=("sina-http",),
        missing_ranges=("HK:盘中行情",),
        degradation_impacts=("港股板块活跃度不可用",),
        sections=("市场总结", "强弱板块", "关注个股", "预测复盘"),
        disclaimer="研究参考，不构成投资建议",
    )

    assert snapshot.missing_ranges == ("HK:盘中行情",)
    assert "研究参考，不构成投资建议" in snapshot.disclaimer

    with pytest.raises(ValidationError):
        DailyReportSnapshot(
            report_id="report-CN-20260715",
            market="CN",
            trade_date="2026-07-15",
            generated_at=datetime(2026, 7, 15, 16, 0, tzinfo=UTC),
            data_version="daily-report-v1",
            source_ids=("sina-http",),
            missing_ranges=(),
            degradation_impacts=(),
            sections=("市场总结",),
            disclaimer="",
        )


def test_每日任务状态机只允许可恢复状态流转() -> None:
    """任务状态必须支持重试、取消、恢复和部分成功，但不能从终态回到运行中。"""

    from stock_agent.domain.daily_report import DailyTaskStateMachine

    machine = DailyTaskStateMachine(status="pending")

    assert machine.transition("running").status == "running"
    assert machine.transition("partial_success").status == "partial_success"
    assert machine.transition("retrying").status == "retrying"
    assert machine.transition("cancelled").status == "cancelled"

    with pytest.raises(ValueError, match="终态任务不能重新运行"):
        machine.transition("running")
