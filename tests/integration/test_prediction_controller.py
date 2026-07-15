"""验证预测控制器阻断不可用当前预测并降级展示历史快照。"""

from datetime import UTC, datetime
from decimal import Decimal

from stock_agent.application.prediction_presenter import PredictionPresentation
from stock_agent.desktop.controllers.prediction_controller import PredictionController
from stock_agent.domain.prediction import FIXED_RESEARCH_DISCLAIMER

预测时点 = datetime(2026, 7, 14, 20, 0, tzinfo=UTC)


def 展示结果(**覆盖: object) -> PredictionPresentation:
    """构造控制器已接收的应用层预测展示结果。"""

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


def test_预测控制器展示当前可用预测并保留研究提示() -> None:
    """当前数据可用时，控制器允许展示当前预测详情。"""

    model = PredictionController().build_workspace(
        current_prediction=展示结果(),
        historical_predictions=(),
    )

    assert model.page_state.status == "READY"
    assert model.current_prediction_allowed is True
    assert model.current_detail is not None
    assert model.current_detail.disclaimer == FIXED_RESEARCH_DISCLAIMER
    assert model.historical_details == ()


def test_预测控制器阻断过期当前预测但保留历史快照只读展示() -> None:
    """过期当前预测不能当作当前结论，历史快照仍可只读查看。"""

    model = PredictionController().build_workspace(
        current_prediction=展示结果(
            freshness_state="STALE",
            display_state="CURRENT_UNAVAILABLE",
        ),
        historical_predictions=(展示结果(display_state="HISTORICAL_SNAPSHOT"),),
    )

    assert model.page_state.status == "STALE"
    assert model.current_prediction_allowed is False
    assert model.current_detail is None
    assert len(model.historical_details) == 1
    assert model.historical_details[0].page_state.status == "HISTORICAL_SNAPSHOT"
    assert model.historical_details[0].show_history_badge is True


def test_预测控制器在权限受限时不展示预测数字() -> None:
    """权限受限时不返回当前或历史预测数字，避免绕过桌面确认边界。"""

    model = PredictionController().build_workspace(
        current_prediction=展示结果(),
        historical_predictions=(展示结果(display_state="HISTORICAL_SNAPSHOT"),),
        permission_granted=False,
    )

    assert model.page_state.status == "PERMISSION_DENIED"
    assert model.current_prediction_allowed is False
    assert model.current_detail is None
    assert model.historical_details == ()
