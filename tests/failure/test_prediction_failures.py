"""验证预测在数据、到期验证和快照版本异常时安全失败，不生成预测或交易。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from stock_agent.domain.market import InstrumentIdentity, Market
from stock_agent.domain.market_rules import CompanyAction, TradingCalendar
from stock_agent.domain.prediction import (
    ActualOutcomeStatus,
    CurrentPredictionUnavailableError,
    ImmutablePredictionSnapshotError,
    PredictionInput,
    PredictionLabelRule,
    PredictionLabelRuleError,
    PredictionOutput,
    PredictionSnapshotStore,
    QuantitativeFactReference,
    resolve_actual_outcome,
)


预测时点 = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
证券 = InstrumentIdentity(market=Market.US, exchange="NASDAQ", display_code="AAPL", currency="USD")
标签规则 = PredictionLabelRule(
    version_id="prediction-label-v1",
    thresholds={1: Decimal("0.01"), 5: Decimal("0.03"), 20: Decimal("0.06")},
)
交易日历 = TradingCalendar(
    market="US",
    version_id="calendar-us-v1",
    trading_days=frozenset({date(2026, 7, 14), date(2026, 7, 15), date(2026, 7, 16)}),
)


def 有效预测输入(**覆盖: object) -> PredictionInput:
    """构造仅含预测时点已可审计事实的输入，供失败边界测试使用。"""

    负载: dict[str, object] = {
        "security_id": 证券,
        "predicted_at": 预测时点,
        "market_time": 预测时点,
        "collected_at": 预测时点,
        "source_id": "local-verified-bars",
        "data_version": "daily-us-v1",
        "feature_version": "features-v1",
        "trading_calendar_version": "calendar-us-v1",
        "calendar_available_at": 预测时点,
        "feature_available_at": 预测时点,
        "feature_cutoff_at": 预测时点,
        "model_version": "baseline-v1",
        "freshness": "REALTIME",
        "time_is_verifiable": True,
        "is_current_data_available": True,
    }
    负载.update(覆盖)
    return PredictionInput(**负载)


def 有效预测输出(**覆盖: object) -> PredictionOutput:
    """构造可用于验证快照不可变性的最小合规输出。"""

    覆盖字段 = ("up_probability", "flat_probability", "down_probability", "confidence")
    负载: dict[str, object] = {
        "security_id": 证券,
        "predicted_at": 预测时点,
        "data_version": "daily-us-v1",
        "feature_version": "features-v1",
        "horizon_trading_days": 5,
        "up_probability": 40.0,
        "flat_probability": 35.0,
        "down_probability": 25.0,
        "confidence": 0.60,
        "primary_evidence": ("本地已验证事实",),
        "risk_factors": ("数据时效会影响研究结论",),
        "freshness": "REALTIME",
        "model_version": "baseline-v1",
        "disclaimer": "研究参考，不构成投资建议",
        "quantitative_fact_references": tuple(
            QuantitativeFactReference(
                reference_type="LOCAL",
                result_id=f"daily-us-v1:NASDAQ:AAPL:{字段}",
                source_id="local-verified-bars",
                security_id=证券,
                prediction_time=预测时点,
                data_version="daily-us-v1",
                model_version="baseline-v1",
                covered_fields=(字段,),
            )
            for 字段 in 覆盖字段
        ),
    }
    负载.update(覆盖)
    return PredictionOutput(**负载)


@pytest.mark.parametrize("新鲜度", ["DELAYED", "STALE", "CLOSED"])
def test_当前预测拒绝延迟过期或闭市行情并说明原因(新鲜度: str) -> None:
    """不具备当前时效的行情不得进入预测，拒绝信息必须可向调用方说明。"""

    with pytest.raises(CurrentPredictionUnavailableError, match="延迟|过期|闭市|当前预测"):
        有效预测输入(freshness=新鲜度)


@pytest.mark.parametrize(
    ("字段", "值"),
    [
        ("time_is_verifiable", False),
        ("source_id", None),
        ("market_time", None),
        ("collected_at", None),
        ("data_version", None),
        ("feature_version", None),
    ],
)
def test_当前预测拒绝不可验证时点或缺少关键来源版本事实(字段: str, 值: object) -> None:
    """来源、市场和采集时点、数据与特征版本任一缺失均必须有明确拒绝原因。"""

    with pytest.raises(CurrentPredictionUnavailableError, match="不可验证|来源|市场时间|采集时间|数据版本|特征版本"):
        有效预测输入(**{字段: 值})


def test_历史快照在当前数据不可用时仍只读可展示() -> None:
    """当前预测被阻断不应删除既有事实；历史记录只能以快照方式查看。"""

    store = PredictionSnapshotStore()
    snapshot = store.append(
        snapshot_id="prediction:NASDAQ:AAPL:2026-07-14T09:30:00Z",
        prediction_input=有效预测输入(),
        prediction_output=有效预测输出(),
    )

    assert snapshot.display_state_for_current_data("STALE").value == "CURRENT_UNAVAILABLE"
    assert snapshot.display_state_for_history().value == "HISTORICAL_SNAPSHOT"
    assert snapshot.prediction_output.up_probability == 40.0


@pytest.mark.parametrize(
    ("到期价格", "到期日", "原因"),
    [
        (None, date(2026, 7, 15), "缺少有效到期价格"),
        (None, date(2026, 7, 15), "停牌或不可成交"),
        (None, date(2026, 7, 18), "到期日非有效交易日"),
    ],
)
def test_无有效到期价格时仅待验证且不产生方向标签(
    到期价格: Decimal | None, 到期日: date, 原因: str
) -> None:
    """缺价、停牌、不可成交或错误到期日都必须保留待验证与明确原因，不能猜测涨跌。"""

    结果 = resolve_actual_outcome(
        prediction_snapshot_id="prediction:NASDAQ:AAPL:2026-07-14T09:30:00Z",
        prediction_time=预测时点,
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=到期日,
        trading_calendar=交易日历,
        trading_calendar_version=交易日历.version_id,
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=到期价格,
        expiry_price_available_at=None,
        validated_at=预测时点 + timedelta(days=1),
        prediction_label_rule=标签规则,
        pending_reason=原因,
    )

    assert 结果.status is ActualOutcomeStatus.PENDING_VALIDATION
    assert 结果.label is None
    assert 结果.pending_reason == 原因


@pytest.mark.parametrize(
    "被篡改字段",
    ["up_probability", "label_rule_version", "model_version", "data_version"],
)
def test_已追加预测快照拒绝覆盖概率或任一版本(被篡改字段: str) -> None:
    """同一快照标识一旦保存，概率和规则、模型、数据版本均不得以重放方式覆盖。"""

    store = PredictionSnapshotStore()
    snapshot_id = "prediction:NASDAQ:AAPL:2026-07-14T09:30:00Z"
    store.append(snapshot_id, 有效预测输入(), 有效预测输出())

    输出覆盖 = {被篡改字段: "tampered-v2"}
    if 被篡改字段 == "up_probability":
        输出覆盖 = {"up_probability": 41.0, "down_probability": 24.0}
    with pytest.raises(ImmutablePredictionSnapshotError, match="追加|覆盖|不可变"):
        store.append(snapshot_id, 有效预测输入(), 有效预测输出(**输出覆盖))


def test_晚到或不匹配版本的到期回填必须拒绝且不能回写历史预测() -> None:
    """回填使用的价格、行动、日历或规则不满足快照时点/版本时，必须拒绝关联记录。"""

    晚到行动 = CompanyAction(
        action_id="split-aapl-20260716",
        action_type="split",
        effective_at=预测时点 + timedelta(days=2),
        version_id="actions-us-v2",
        source_id="authorized-source",
    )

    with pytest.raises(PredictionLabelRuleError, match="可得时点|公司行动|日历版本|规则版本|回写"):
        resolve_actual_outcome(
            prediction_snapshot_id="prediction:NASDAQ:AAPL:2026-07-14T09:30:00Z",
            prediction_time=预测时点,
            horizon_trading_days=1,
            reference_trading_day=date(2026, 7, 14),
            expiry_trading_day=date(2026, 7, 15),
            trading_calendar=交易日历,
            trading_calendar_version="calendar-us-v2",
            reference_total_return_adjusted_price=Decimal("100"),
            expiry_total_return_adjusted_price=Decimal("101"),
            expiry_price_available_at=预测时点 + timedelta(days=3),
            validated_at=预测时点 + timedelta(days=3),
            prediction_label_rule=标签规则,
            company_actions=(晚到行动,),
        )
