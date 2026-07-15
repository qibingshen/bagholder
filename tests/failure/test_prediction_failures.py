"""验证预测在数据、到期验证和快照版本异常时安全失败，不生成预测或交易。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest
from pydantic import ValidationError

from stock_agent.domain.market import InstrumentIdentity, Market
from stock_agent.domain.market_rules import CompanyAction, TradingCalendar
from stock_agent.domain.prediction import (
    ActualOutcomeStatus,
    CurrentPredictionUnavailableError,
    ImmutablePredictionSnapshotError,
    PredictionInput,
    PredictionLabelRule,
    PredictionOutput,
    PredictionSnapshotStore,
    QuantitativeFactReference,
    QuantitativeFieldEvidence,
    issue_local_outcome_fact,
    outcome_fact_value,
    quantitative_value_hash,
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
    trading_days=frozenset(
        {
            date(2026, 7, 14),
            date(2026, 7, 15),
            date(2026, 7, 16),
            date(2026, 7, 17),
            date(2026, 7, 20),
            date(2026, 7, 21),
        }
    ),
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
        "prediction_label_rule_version": "prediction-label-v1",
        "freshness": "REALTIME",
        "time_is_verifiable": True,
        "is_current_data_available": True,
    }
    负载.update(覆盖)
    return PredictionInput(**负载)


def 有效预测输出(**覆盖: object) -> PredictionOutput:
    """构造可用于验证快照不可变性的最小合规输出。"""

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
        "label_rule_version": "prediction-label-v1",
        "disclaimer": "研究参考，不构成投资建议",
    }
    负载.update(覆盖)
    量化字段 = ("up_probability", "flat_probability", "down_probability", "confidence")
    负载["quantitative_fact_references"] = tuple(
        QuantitativeFactReference(
            reference_type="LOCAL",
            result_id=f"{负载['data_version']}:NASDAQ:AAPL:{字段}",
            tool_name="local_fact_store",
            tool_version="v1",
            called_at=预测时点,
            data_as_of=预测时点,
            market_time=预测时点,
            collected_at=预测时点,
            available_at=预测时点,
            result_anchor=f"local://facts/{负载['data_version']}:NASDAQ:AAPL:{字段}",
            source_id="local-verified-bars",
            security_id=证券,
            prediction_time=预测时点,
            data_version=str(负载["data_version"]),
            feature_version=str(负载["feature_version"]),
            model_version=str(负载["model_version"]),
            label_rule_version=str(负载["label_rule_version"]),
            covered_fields=(字段,),
            field_evidence=(
                QuantitativeFieldEvidence(
                    field_name=字段,
                    numeric_value=Decimal(str(负载[字段])),
                    value_hash=quantitative_value_hash(字段, Decimal(str(负载[字段]))),
                    value_evidence="本地可复核事实",
                ),
            ),
        )
        for 字段 in 量化字段
    )
    return PredictionOutput(**负载)


def 有效到期结果(**覆盖: object):
    """构造可独立追加的到期结果；其事实必须能追溯到预测快照。"""

    验证时点 = 预测时点 + timedelta(days=8)
    负载: dict[str, object] = {
        "prediction_snapshot_id": "prediction:NASDAQ:AAPL:2026-07-14T09:30:00Z",
        "prediction_time": 预测时点,
        "horizon_trading_days": 5,
        "reference_trading_day": date(2026, 7, 14),
        "expiry_trading_day": date(2026, 7, 21),
        "trading_calendar": 交易日历,
        "trading_calendar_version": "calendar-us-v1",
        "snapshot_trading_calendar_version": "calendar-us-v1",
        "calendar_available_at": 验证时点,
        "reference_total_return_adjusted_price": Decimal("100"),
        "expiry_total_return_adjusted_price": Decimal("101"),
        "expiry_price_available_at": 验证时点,
        "validated_at": 验证时点,
        "prediction_label_rule": 标签规则,
        "snapshot_label_rule_version": "prediction-label-v1",
        "label_rule_available_at": 验证时点,
        "company_actions": (),
        "company_actions_available_at": 验证时点,
    }
    负载.update(覆盖)
    到期事实值 = {
        "REFERENCE_PRICE": 负载["reference_total_return_adjusted_price"],
        "EXPIRY_PRICE": 负载["expiry_total_return_adjusted_price"],
        "REFERENCE_TRADABILITY": "TRADABLE",
        "EXPIRY_TRADABILITY": "TRADABLE",
        "TRADING_CALENDAR": 负载["trading_calendar"],
        "LABEL_RULE": 负载["prediction_label_rule"],
        "COMPANY_ACTIONS": tuple(负载["company_actions"]),
    }
    到期事实版本 = {
        "REFERENCE_PRICE": "daily-us-v1",
        "EXPIRY_PRICE": "daily-us-v1",
        "REFERENCE_TRADABILITY": "daily-us-v1",
        "EXPIRY_TRADABILITY": "daily-us-v1",
        "TRADING_CALENDAR": 负载["trading_calendar_version"],
        "LABEL_RULE": 负载["prediction_label_rule"].version_id,
        "COMPANY_ACTIONS": "company-actions-v1",
    }
    if all(value is not None for value in 到期事实值.values()):
        负载["outcome_fact_references"] = tuple(
            issue_local_outcome_fact(
                fact_type=事实类型,
                security_id=证券,
                prediction_snapshot_id=str(负载["prediction_snapshot_id"]),
                prediction_time=预测时点,
                reference_type="LOCAL",
                source_id="local-verified-history",
                tool_name="local_fact_store",
                tool_version="v1",
                market_time=(
                    预测时点
                    if 事实类型 == "REFERENCE_PRICE"
                    else datetime.combine(
                        负载["expiry_trading_day"], datetime.min.time(), tzinfo=UTC
                    ).replace(hour=12)
                    if 事实类型 == "EXPIRY_PRICE"
                    else 验证时点
                ),
                collected_at=(
                    预测时点
                    if 事实类型 == "REFERENCE_PRICE"
                    else datetime.combine(
                        负载["expiry_trading_day"], datetime.min.time(), tzinfo=UTC
                    ).replace(hour=12)
                    if 事实类型 == "EXPIRY_PRICE"
                    else 验证时点
                ),
                available_at=(
                    预测时点
                    if 事实类型 == "REFERENCE_PRICE"
                    else datetime.combine(
                        负载["expiry_trading_day"], datetime.min.time(), tzinfo=UTC
                    ).replace(hour=12)
                    if 事实类型 == "EXPIRY_PRICE"
                    else 验证时点
                ),
                version_id=str(到期事实版本[事实类型]),
                result_id=f"{事实类型}:{到期事实版本[事实类型]}",
                result_anchor=f"local://outcomes/{事实类型}:{到期事实版本[事实类型]}",
                fact_value=outcome_fact_value(事实类型, 到期事实值[事实类型]),
                value_hash=sha256(
                    f"{事实类型}:{outcome_fact_value(事实类型, 到期事实值[事实类型])}".encode()
                ).hexdigest(),
            )
            for 事实类型 in (
                "REFERENCE_PRICE",
                "EXPIRY_PRICE",
                "REFERENCE_TRADABILITY",
                "EXPIRY_TRADABILITY",
                "TRADING_CALENDAR",
                "LABEL_RULE",
                "COMPANY_ACTIONS",
            )
        )
        负载["security_id"] = 证券
        负载["price_data_version"] = "daily-us-v1"
    return resolve_actual_outcome(**负载)


@pytest.mark.parametrize("新鲜度", ["DELAYED", "STALE", "CLOSED"])
def test_当前预测拒绝延迟过期或闭市行情并说明原因(新鲜度: str) -> None:
    """不具备当前时效的行情不得进入预测，拒绝信息必须可向调用方说明。"""

    with pytest.raises(CurrentPredictionUnavailableError, match="延迟|过期|闭市|当前预测"):
        有效预测输入(freshness=新鲜度)


@pytest.mark.parametrize(
    ("字段", "值", "异常类型"),
    [
        ("time_is_verifiable", False, ValidationError),
        ("source_id", None, CurrentPredictionUnavailableError),
        ("market_time", None, ValidationError),
        ("collected_at", None, ValidationError),
        ("data_version", None, ValidationError),
        ("feature_version", None, ValidationError),
    ],
)
def test_当前预测按输入类型拒绝不可验证时点或缺少关键来源版本事实(
    字段: str, 值: object, 异常类型: type[ValueError]
) -> None:
    """来源、市场和采集时点、数据与特征版本任一缺失均必须有明确拒绝原因。"""

    错误标识 = {
        "market_time": "market_time",
        "collected_at": "collected_at",
        "data_version": "data_version",
        "feature_version": "feature_version",
    }.get(字段, "不可验证|来源")
    with pytest.raises(异常类型, match=错误标识):
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


def test_到期结果只能独立追加关联快照且不能改变原快照() -> None:
    """到期结果不是预测快照的更新；追加前后快照的事实字段必须逐项不变。"""

    store = PredictionSnapshotStore()
    snapshot = store.append(
        "prediction:NASDAQ:AAPL:2026-07-14T09:30:00Z",
        有效预测输入(),
        有效预测输出(),
        trading_calendar=交易日历,
        prediction_label_rule=标签规则,
    )
    追加前 = (
        snapshot.prediction_output.up_probability,
        snapshot.prediction_output.flat_probability,
        snapshot.prediction_output.down_probability,
        snapshot.prediction_input.data_version,
        snapshot.prediction_input.model_version,
        snapshot.prediction_input.prediction_label_rule_version,
        snapshot.generated_at,
    )
    到期结果 = 有效到期结果()

    已关联结果 = store.append_actual_outcome(到期结果)

    assert 已关联结果.prediction_snapshot_id == snapshot.snapshot_id
    assert store.actual_outcomes_for(snapshot.snapshot_id) == (到期结果,)
    assert (
        snapshot.prediction_output.up_probability,
        snapshot.prediction_output.flat_probability,
        snapshot.prediction_output.down_probability,
        snapshot.prediction_input.data_version,
        snapshot.prediction_input.model_version,
        snapshot.prediction_input.prediction_label_rule_version,
        snapshot.generated_at,
    ) == 追加前
    with pytest.raises(ImmutablePredictionSnapshotError, match="追加|覆盖|不可变|重复"):
        store.append_actual_outcome(到期结果)


def _公司行动(可得时点: datetime) -> CompanyAction:
    """构造到期回填要引用的公司行动，并显式记录其可得时点。"""

    return CompanyAction(
        action_id="split-aapl-20260715",
        action_type="split",
        effective_at=datetime(2026, 7, 15, 9, 30, tzinfo=UTC),
        available_at=可得时点,
        version_id="actions-us-v1",
        source_id="authorized-source",
    )


@pytest.mark.parametrize(
    ("违规名称", "覆盖"),
    [
        (
            "价格可得时点晚于验证边界",
            {"expiry_price_available_at": 预测时点 + timedelta(days=8, seconds=1)},
        ),
        (
            "公司行动可得时点晚于验证边界",
            {"company_actions": (_公司行动(预测时点 + timedelta(days=8, seconds=1)),)},
        ),
        (
            "交易日历可得时点晚于验证边界",
            {"calendar_available_at": 预测时点 + timedelta(days=8, seconds=1)},
        ),
        (
            "标签规则可得时点晚于验证边界",
            {"label_rule_available_at": 预测时点 + timedelta(days=8, seconds=1)},
        ),
        ("交易日历版本与快照不匹配", {"trading_calendar_version": "calendar-us-v2"}),
        (
            "标签规则版本与快照不匹配",
            {
                "prediction_label_rule": PredictionLabelRule(
                    version_id="prediction-label-v2",
                    thresholds={1: Decimal("0.01"), 5: Decimal("0.03"), 20: Decimal("0.06")},
                )
            },
        ),
    ],
)
def test_到期回填中每项晚到或版本不匹配均必须独立拒绝(
    违规名称: str, 覆盖: dict[str, object]
) -> None:
    """价格、行动、日历和规则均不能以晚到或错版事实回填历史预测。"""

    assert 有效到期结果(**覆盖).status is ActualOutcomeStatus.PENDING_VALIDATION
