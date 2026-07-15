"""验证历史预测复盘页面状态。"""

from decimal import Decimal


def test_历史复盘页面展示基准比较和待验证状态() -> None:
    """历史复盘页面必须区分已验证结果和待验证预测。"""

    from stock_agent.desktop.pages.history_review_page import HistoryReviewRow, HistoryReviewView

    view = HistoryReviewView(
        rows=(
            HistoryReviewRow(
                snapshot_id="pred-1",
                outcome_status="validated",
                model_brier=Decimal("0.21"),
                baseline_brier=Decimal("0.25"),
            ),
            HistoryReviewRow(
                snapshot_id="pred-2",
                outcome_status="pending_validation",
                model_brier=None,
                baseline_brier=None,
            ),
        )
    )

    assert view.rows[0].beats_baseline is True
    assert view.rows[1].show_pending_badge is True
    assert view.has_pending_validation is True
