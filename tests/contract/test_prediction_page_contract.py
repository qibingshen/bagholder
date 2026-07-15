"""验证预测详情页状态模型展示快照、历史和待验证状态。"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from stock_agent.application.prediction_presenter import PredictionPresentation
from stock_agent.desktop.pages.prediction_page import PredictionDetailView, PredictionPageState
from stock_agent.domain.prediction import FIXED_RESEARCH_DISCLAIMER

预测时点 = datetime(2026, 7, 14, 20, 0, tzinfo=UTC)


def 展示结果(**覆盖: object) -> PredictionPresentation:
    """构造预测页可渲染的展示结果。"""

    负载 = {
        "snapshot_id": "prediction:US:NASDAQ:AAPL:2026-07-14T20:00:00Z:5d",
        "security_key": "US:NASDAQ:AAPL",
        "horizon_trading_days": 5,
        "probabilities": {
            "up": Decimal("34.0"),
            "flat": Decimal("33.0"),
            "down": Decimal("33.0"),
        },
        "confidence": Decimal("0.5"),
        "primary_evidence": ("本地特征快照已按预测时点截断",),
        "risk_factors": ("简单基准存在模型偏差",),
        "freshness_state": "NEAR_REALTIME",
        "display_state": "CURRENT_AVAILABLE",
        "version_summary": {
            "data_version": "daily-us-v1",
            "feature_version": "features-v1",
            "model_version": "baseline-v1",
            "label_rule_version": "prediction-label-v1",
        },
        "disclaimer": FIXED_RESEARCH_DISCLAIMER,
        "fact_references_by_field": {},
    }
    负载.update(覆盖)
    return PredictionPresentation(**负载)


@pytest.mark.parametrize(
    "state",
    [
        "EMPTY",
        "LOADING",
        "OFFLINE",
        "PERMISSION_DENIED",
        "STALE",
        "READY",
        "PENDING_VALIDATION",
        "HISTORICAL_SNAPSHOT",
    ],
)
def test_预测页状态都有中文用户说明且不会默认允许当前预测(state: str) -> None:
    """预测页所有状态都必须可解释，非 READY 状态不得打开当前预测入口。"""

    page_state = PredictionPageState(status=state)

    assert page_state.user_message
    assert any("\u4e00" <= character <= "\u9fff" for character in page_state.user_message)
    assert page_state.allow_current_prediction is (state == "READY")


def test_预测详情视图展示概率版本风险和固定免责声明() -> None:
    """预测详情页必须完整展示概率、依据、风险、版本和固定风险提示。"""

    detail = PredictionDetailView.from_presentation(展示结果())

    assert detail.page_state.status == "READY"
    assert detail.probability_rows == (
        ("上涨", Decimal("34.0")),
        ("震荡", Decimal("33.0")),
        ("下跌", Decimal("33.0")),
    )
    assert detail.confidence == Decimal("0.5")
    assert detail.version_summary["model_version"] == "baseline-v1"
    assert detail.disclaimer == FIXED_RESEARCH_DISCLAIMER
    assert detail.show_history_badge is False


def test_预测详情页对过期当前预测降级但仍可查看历史快照() -> None:
    """过期数据不能作为当前预测展示，但历史快照仍可只读查看。"""

    stale = PredictionDetailView.from_presentation(
        展示结果(freshness_state="STALE", display_state="CURRENT_UNAVAILABLE")
    )
    historical = PredictionDetailView.from_presentation(
        展示结果(display_state="HISTORICAL_SNAPSHOT"),
        historical=True,
    )

    assert stale.page_state.status == "STALE"
    assert stale.page_state.allow_current_prediction is False
    assert historical.page_state.status == "HISTORICAL_SNAPSHOT"
    assert historical.show_history_badge is True
    assert historical.disclaimer == FIXED_RESEARCH_DISCLAIMER


def test_预测详情页能显示到期结果待验证状态() -> None:
    """未到期或事实不完整时，页面必须显示待验证而不是提前判定方向。"""

    detail = PredictionDetailView.from_presentation(展示结果(), outcome_status="PENDING_VALIDATION")

    assert detail.page_state.status == "PENDING_VALIDATION"
    assert detail.outcome_status == "PENDING_VALIDATION"
    assert "待验证" in detail.page_state.user_message
