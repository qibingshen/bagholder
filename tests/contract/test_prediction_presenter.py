"""验证预测展示组装不补造数字且保留风险提示和版本元数据。"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from stock_agent.application.prediction_presenter import (
    PredictionPresentationError,
    PredictionPresenter,
)
from stock_agent.domain.market import InstrumentIdentity, Market
from stock_agent.domain.prediction import (
    FIXED_RESEARCH_DISCLAIMER,
    PredictionOutput,
    PredictionSnapshot,
    QuantitativeFactReference,
    QuantitativeFieldEvidence,
    quantitative_value_hash,
)

预测时点 = datetime(2026, 7, 14, 20, 0, tzinfo=UTC)
证券 = InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD")


def 事实引用(字段: str, 数值: Decimal) -> QuantitativeFactReference:
    """构造覆盖单个展示数字的本地事实引用。"""

    return QuantitativeFactReference(
        reference_type="LOCAL",
        result_id=f"baseline:{字段}",
        tool_name="local_simple_baseline",
        tool_version="v1",
        called_at=预测时点,
        data_as_of=预测时点,
        market_time=预测时点,
        collected_at=预测时点,
        available_at=预测时点,
        result_anchor=f"local://predictions/baseline/{字段}",
        source_id="local-feature-store",
        security_id=证券,
        prediction_time=预测时点,
        data_version="daily-us-v1",
        feature_version="features-v1",
        model_version="baseline-v1",
        label_rule_version="prediction-label-v1",
        covered_fields=(字段,),
        field_evidence=(
            QuantitativeFieldEvidence(
                field_name=字段,
                numeric_value=数值,
                value_hash=quantitative_value_hash(字段, 数值),
                value_evidence="本地简单基准可复核事实",
            ),
        ),
    )


def 预测输出(**覆盖: object) -> PredictionOutput:
    """构造已通过领域层校验的预测输出。"""

    负载 = {
        "security_id": 证券,
        "predicted_at": 预测时点,
        "data_version": "daily-us-v1",
        "feature_version": "features-v1",
        "horizon_trading_days": 5,
        "up_probability": 34.0,
        "flat_probability": 33.0,
        "down_probability": 33.0,
        "confidence": 0.5,
        "primary_evidence": ("本地特征快照已按预测时点截断",),
        "risk_factors": ("简单基准存在模型偏差",),
        "freshness": "NEAR_REALTIME",
        "model_version": "baseline-v1",
        "label_rule_version": "prediction-label-v1",
        "disclaimer": FIXED_RESEARCH_DISCLAIMER,
        "quantitative_fact_references": (
            事实引用("up_probability", Decimal("34")),
            事实引用("flat_probability", Decimal("33")),
            事实引用("down_probability", Decimal("33")),
            事实引用("confidence", Decimal("0.5")),
        ),
    }
    负载.update(覆盖)
    return PredictionOutput(**负载)


def 预测快照(**输出覆盖: object) -> PredictionSnapshot:
    """构造展示层所需的最小预测快照。"""

    return PredictionSnapshot(
        snapshot_id="prediction:US:NASDAQ:AAPL:2026-07-14T20:00:00Z:5d",
        prediction_input=object(),
        prediction_output=预测输出(**输出覆盖),
        generated_at=预测时点,
        trading_calendar_fact_value="calendar",
        label_rule_fact_value="label-rule",
    )


def test_预测展示组装复制概率置信度并保留数字溯源() -> None:
    """展示层只能复制领域输出里的数字，不能重新计算或补造。"""

    presentation = PredictionPresenter().present(预测快照())

    assert presentation.probabilities == {
        "up": Decimal("34.0"),
        "flat": Decimal("33.0"),
        "down": Decimal("33.0"),
    }
    assert presentation.confidence == Decimal("0.5")
    assert presentation.disclaimer == FIXED_RESEARCH_DISCLAIMER
    assert presentation.freshness_state == "NEAR_REALTIME"
    assert presentation.display_state == "CURRENT_AVAILABLE"
    assert presentation.version_summary == {
        "data_version": "daily-us-v1",
        "feature_version": "features-v1",
        "model_version": "baseline-v1",
        "label_rule_version": "prediction-label-v1",
    }
    assert set(presentation.fact_references_by_field) == {
        "up_probability",
        "flat_probability",
        "down_probability",
        "confidence",
    }


def test_预测展示组装拒绝缺少任一数字事实引用的快照() -> None:
    """即使领域对象被错误构造，展示层也必须复核数字溯源。"""

    snapshot = 预测快照()
    snapshot.prediction_output.quantitative_fact_references = tuple(
        reference
        for reference in snapshot.prediction_output.quantitative_fact_references
        if "confidence" not in reference.covered_fields
    )

    with pytest.raises(PredictionPresentationError, match="事实引用|confidence"):
        PredictionPresenter().present(snapshot)


def test_预测展示组装拒绝收益承诺或买卖指令文案() -> None:
    """展示层二次检查解释文案，避免后续组装混入投资建议。"""

    snapshot = 预测快照()
    snapshot.prediction_output.risk_factors = ("建议立即买入",)

    with pytest.raises(PredictionPresentationError, match="投资建议|买卖|承诺"):
        PredictionPresenter().present(snapshot)
