"""验证预测应用用例只使用预测时点可得事实生成简单基准快照。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from stock_agent.application.prediction_service import (
    FeatureSnapshotFact,
    PredictionGenerationCommand,
    PredictionService,
)
from stock_agent.domain.market import InstrumentIdentity, Market
from stock_agent.domain.market_rules import TradingCalendar
from stock_agent.domain.prediction import (
    FIXED_RESEARCH_DISCLAIMER,
    CurrentPredictionUnavailableError,
    PredictionLabelRule,
    PredictionSnapshotStore,
)

预测时点 = datetime(2026, 7, 14, 20, 0, tzinfo=UTC)
证券 = InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD")
日历 = TradingCalendar(
    market="US",
    version_id="calendar-us-v1",
    trading_days=frozenset({date(2026, 7, 14), date(2026, 7, 15), date(2026, 7, 16)}),
)
标签规则 = PredictionLabelRule(
    version_id="prediction-label-v1",
    thresholds={1: Decimal("0.01"), 5: Decimal("0.03"), 20: Decimal("0.06")},
)


def 特征快照(**覆盖: object) -> FeatureSnapshotFact:
    """构造预测时点前已经可得的本地特征事实。"""

    负载 = {
        "snapshot_id": "feature:US:NASDAQ:AAPL:2026-07-14",
        "security_id": 证券,
        "feature_version": "features-v1",
        "source_id": "local-feature-store",
        "market_time": datetime(2026, 7, 14, 16, 0, tzinfo=UTC),
        "collected_at": datetime(2026, 7, 14, 16, 5, tzinfo=UTC),
        "available_at": datetime(2026, 7, 14, 16, 10, tzinfo=UTC),
        "cutoff_at": datetime(2026, 7, 14, 16, 0, tzinfo=UTC),
        "values": {"five_day_momentum": Decimal("0.012"), "volume_ratio": Decimal("1.25")},
    }
    负载.update(覆盖)
    return FeatureSnapshotFact(**负载)


def 生成命令(**覆盖: object) -> PredictionGenerationCommand:
    """返回最小可生成的简单基准预测命令。"""

    负载 = {
        "security_id": 证券,
        "predicted_at": 预测时点,
        "market_time": datetime(2026, 7, 14, 16, 0, tzinfo=UTC),
        "collected_at": datetime(2026, 7, 14, 16, 5, tzinfo=UTC),
        "available_at": datetime(2026, 7, 14, 16, 10, tzinfo=UTC),
        "source_id": "local-daily-bars",
        "data_version": "daily-us-v1",
        "model_version": "baseline-v1",
        "horizon_trading_days": 5,
        "freshness": "NEAR_REALTIME",
        "reference_total_return_adjusted_price": Decimal("100"),
        "reference_price_available_at": datetime(2026, 7, 14, 16, 10, tzinfo=UTC),
        "trading_calendar": 日历,
        "calendar_available_at": datetime(2026, 7, 14, 8, 0, tzinfo=UTC),
        "prediction_label_rule": 标签规则,
        "label_rule_available_at": datetime(2026, 7, 14, 8, 0, tzinfo=UTC),
        "feature_snapshot": 特征快照(),
        "primary_evidence": ("本地特征快照已按预测时点截断",),
        "risk_factors": ("简单基准存在模型偏差",),
    }
    负载.update(覆盖)
    return PredictionGenerationCommand(**负载)


def test_预测服务生成简单基准概率并追加不可变快照() -> None:
    """应用用例必须把输入、输出、日历和规则绑定成同一份快照。"""

    store = PredictionSnapshotStore()
    service = PredictionService(snapshot_store=store)

    snapshot = service.generate_simple_baseline_snapshot(生成命令())

    assert snapshot.snapshot_id == "prediction:US:NASDAQ:AAPL:2026-07-14T20:00:00Z:5d"
    assert snapshot.prediction_input.feature_version == "features-v1"
    assert snapshot.prediction_input.feature_cutoff_at == datetime(2026, 7, 14, 16, 0, tzinfo=UTC)
    assert snapshot.prediction_output.up_probability == 34.0
    assert snapshot.prediction_output.flat_probability == 33.0
    assert snapshot.prediction_output.down_probability == 33.0
    assert snapshot.prediction_output.confidence == 0.5
    assert snapshot.prediction_output.disclaimer == FIXED_RESEARCH_DISCLAIMER
    assert snapshot.trading_calendar_fact_value is not None
    assert snapshot.label_rule_fact_value is not None
    assert store.actual_outcomes_for(snapshot.snapshot_id) == ()


def test_预测服务为每个量化数字绑定本地事实引用() -> None:
    """大模型后续解释只能引用这些结构化事实，不能重新编造概率或置信度。"""

    service = PredictionService(snapshot_store=PredictionSnapshotStore())
    snapshot = service.generate_simple_baseline_snapshot(生成命令())
    references = snapshot.prediction_output.quantitative_fact_references
    evidence_by_field = {
        evidence.field_name: evidence.numeric_value
        for reference in references
        for evidence in reference.field_evidence
    }

    assert evidence_by_field == {
        "up_probability": Decimal("34"),
        "flat_probability": Decimal("33"),
        "down_probability": Decimal("33"),
        "confidence": Decimal("0.5"),
    }
    assert {reference.reference_type for reference in references} == {"LOCAL"}
    assert all(reference.result_anchor.startswith("local://") for reference in references)
    assert all(reference.data_as_of <= 预测时点 for reference in references)


@pytest.mark.parametrize(
    ("字段", "值"),
    [
        ("available_at", 预测时点 + timedelta(seconds=1)),
        ("cutoff_at", 预测时点 + timedelta(seconds=1)),
    ],
)
def test_预测服务拒绝预测时点后才可得的特征事实(字段: str, 值: datetime) -> None:
    """特征可得时点和截断时点都不得晚于预测时点，避免未来数据泄漏。"""

    with pytest.raises(
        (CurrentPredictionUnavailableError, ValidationError),
        match="特征|预测时点|未来",
    ):
        service = PredictionService(snapshot_store=PredictionSnapshotStore())
        service.generate_simple_baseline_snapshot(生成命令(feature_snapshot=特征快照(**{字段: 值})))


def test_预测服务拒绝与目标证券不匹配的特征快照() -> None:
    """本地特征即使存在，也必须与目标证券逐项绑定。"""

    other_security = InstrumentIdentity(Market.US, "NASDAQ", "MSFT", "USD")
    with pytest.raises(
        (CurrentPredictionUnavailableError, ValidationError),
        match="特征|证券|绑定",
    ):
        service = PredictionService(snapshot_store=PredictionSnapshotStore())
        service.generate_simple_baseline_snapshot(
            生成命令(feature_snapshot=特征快照(security_id=other_security))
        )


def test_预测服务不接受非当前可用行情生成当前预测() -> None:
    """延迟、过期或不可验证行情不能被伪装成当前预测快照。"""

    command = 生成命令(freshness="STALE")

    with pytest.raises(CurrentPredictionUnavailableError, match="当前预测|过期|延迟|闭市"):
        PredictionService(
            snapshot_store=PredictionSnapshotStore()
        ).generate_simple_baseline_snapshot(command)
