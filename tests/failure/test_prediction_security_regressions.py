"""覆盖 T050 独立审查发现的预测领域安全回归。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest
from pydantic import ValidationError

from stock_agent.domain.market import InstrumentIdentity, Market
from stock_agent.domain.market_rules import TradingCalendar
from stock_agent.domain.prediction import (
    ActualOutcomeStatus,
    OutcomeFactReference,
    PredictionInput,
    PredictionLabelRule,
    PredictionOutput,
    PredictionSnapshotStore,
    QuantitativeFactReference,
    QuantitativeFieldEvidence,
    quantitative_value_hash,
    resolve_actual_outcome,
)

时间 = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
证券 = InstrumentIdentity(market=Market.US, exchange="NASDAQ", display_code="AAPL", currency="USD")
日历 = TradingCalendar(
    market="US",
    version_id="calendar-us-v1",
    trading_days=frozenset({date(2026, 7, 14), date(2026, 7, 15)}),
)
规则 = PredictionLabelRule(
    version_id="label-v1", thresholds={1: Decimal("0.01"), 5: Decimal("0.03"), 20: Decimal("0.06")}
)


def _输入(**覆盖: object) -> PredictionInput:
    负载: dict[str, object] = {
        "security_id": 证券,
        "predicted_at": 时间,
        "market_time": 时间,
        "collected_at": 时间,
        "source_id": "local-bars",
        "data_version": "daily-v1",
        "feature_version": "feature-v1",
        "trading_calendar_version": "calendar-us-v1",
        "calendar_available_at": 时间,
        "feature_available_at": 时间,
        "feature_cutoff_at": 时间,
        "model_version": "baseline-v1",
        "prediction_label_rule_version": "label-v1",
        "is_current_data_available": True,
    }
    负载.update(覆盖)
    return PredictionInput(**负载)


def _引用(field: str) -> QuantitativeFactReference:
    value = {
        "up_probability": "40",
        "flat_probability": "35",
        "down_probability": "25",
        "confidence": "0.6",
    }[field]
    return QuantitativeFactReference(
        reference_type="LOCAL",
        result_id=f"fact-{field}",
        tool_name="local_fact_store",
        tool_version="v1",
        called_at=时间,
        data_as_of=时间,
        result_anchor=f"local://facts/fact-{field}",
        source_id="local-bars",
        security_id=证券,
        prediction_time=时间,
        data_version="daily-v1",
        feature_version="feature-v1",
        model_version="baseline-v1",
        label_rule_version="label-v1",
        covered_fields=(field,),
        field_evidence=(
            QuantitativeFieldEvidence(
                field_name=field,
                numeric_value=Decimal(value),
                value_hash=quantitative_value_hash(field, Decimal(value)),
                value_evidence="本地可复核事实",
            ),
        ),
    )


def _输出(**覆盖: object) -> PredictionOutput:
    负载: dict[str, object] = {
        "security_id": 证券,
        "predicted_at": 时间,
        "data_version": "daily-v1",
        "feature_version": "feature-v1",
        "horizon_trading_days": 1,
        "up_probability": 40.0,
        "flat_probability": 35.0,
        "down_probability": 25.0,
        "confidence": 0.6,
        "primary_evidence": ("本地事实",),
        "risk_factors": ("波动风险",),
        "freshness": "REALTIME",
        "model_version": "baseline-v1",
        "label_rule_version": "label-v1",
        "disclaimer": "研究参考，不构成投资建议",
        "quantitative_fact_references": tuple(
            _引用(field)
            for field in ("up_probability", "flat_probability", "down_probability", "confidence")
        ),
    }
    负载.update(覆盖)
    return PredictionOutput(**负载)


def test_事实引用拒绝覆盖字段单独声称数值证据() -> None:
    with pytest.raises(ValidationError, match="数值|哈希|证据|引用"):
        _输出(
            quantitative_fact_references=tuple(
                _引用(field).model_copy(update={"field_evidence": ()})
                for field in (
                    "up_probability",
                    "flat_probability",
                    "down_probability",
                    "confidence",
                )
            )
        )


def test_事实引用拒绝特征版本不匹配() -> None:
    with pytest.raises(ValidationError, match="特征版本|引用"):
        _输出(
            quantitative_fact_references=tuple(
                _引用(field).model_copy(update={"feature_version": "feature-v2"})
                for field in (
                    "up_probability",
                    "flat_probability",
                    "down_probability",
                    "confidence",
                )
            )
        )


def test_已有价格的非交易到期日保持待验证() -> None:
    outcome = resolve_actual_outcome(
        prediction_snapshot_id="snapshot-1",
        prediction_time=时间,
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=date(2026, 7, 16),
        trading_calendar=日历,
        trading_calendar_version="calendar-us-v1",
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=Decimal("101"),
        expiry_price_available_at=时间 + timedelta(days=2),
        validated_at=时间 + timedelta(days=2),
        prediction_label_rule=规则,
    )
    assert outcome.status is ActualOutcomeStatus.PENDING_VALIDATION


def test_到期结果缺少结构化事实引用时不能验证() -> None:
    """到期价格、日历和规则没有可审计来源时不能产生历史标签。"""

    outcome = resolve_actual_outcome(
        prediction_snapshot_id="snapshot-facts",
        prediction_time=时间,
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=date(2026, 7, 15),
        trading_calendar=日历,
        trading_calendar_version="calendar-us-v1",
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=Decimal("101"),
        expiry_price_available_at=时间 + timedelta(days=1),
        validated_at=时间 + timedelta(days=1),
        prediction_label_rule=规则,
    )
    assert outcome.status is ActualOutcomeStatus.PENDING_VALIDATION
    assert outcome.fact_references == ()


def test_到期结果保存完整的结构化事实引用() -> None:
    """已验证结果必须持久保留价格、日历与规则的事实来源。"""

    validated_at = 时间 + timedelta(days=2)
    facts = tuple(
        OutcomeFactReference(
            fact_type=fact_type,
            reference_type="LOCAL",
            source_id="local-history",
            tool_name="local_fact_store",
            tool_version="v1",
            market_time=validated_at,
            collected_at=validated_at,
            available_at=validated_at,
            version_id="daily-v1" if "PRICE" in fact_type else "calendar-us-v1",
            result_id=f"result-{fact_type}",
            result_anchor=f"local://outcomes/result-{fact_type}",
            fact_value=f"{fact_type}:daily-v1",
            value_hash=sha256(f"{fact_type}:{fact_type}:daily-v1".encode()).hexdigest(),
        )
        for fact_type in ("REFERENCE_PRICE", "EXPIRY_PRICE", "TRADING_CALENDAR", "LABEL_RULE")
    )
    outcome = resolve_actual_outcome(
        prediction_snapshot_id="snapshot-facts",
        prediction_time=时间,
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=date(2026, 7, 15),
        trading_calendar=日历,
        trading_calendar_version="calendar-us-v1",
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=Decimal("101"),
        expiry_price_available_at=validated_at,
        validated_at=validated_at,
        prediction_label_rule=规则,
        outcome_fact_references=facts,
    )
    assert outcome.status is ActualOutcomeStatus.VALIDATED
    assert outcome.fact_references == facts


def test_快照追加对调用方嵌套对象防御拷贝() -> None:
    store = PredictionSnapshotStore()
    预测输入 = _输入()
    预测输出 = _输出()
    snapshot = store.append("snapshot-1", 预测输入, 预测输出)
    预测输出.primary_evidence = ("被调用方修改",)
    assert snapshot.prediction_output.primary_evidence == ("本地事实",)


def test_结果追加拒绝非快照派生的预测时点() -> None:
    store = PredictionSnapshotStore()
    store.append("snapshot-1", _输入(), _输出())
    outcome = resolve_actual_outcome(
        prediction_snapshot_id="snapshot-1",
        prediction_time=时间 + timedelta(seconds=1),
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=date(2026, 7, 15),
        trading_calendar=日历,
        trading_calendar_version="calendar-us-v1",
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=Decimal("101"),
        expiry_price_available_at=时间 + timedelta(days=1),
        validated_at=时间 + timedelta(days=1),
        prediction_label_rule=规则,
    )
    with pytest.raises(ValueError, match="预测时点|快照"):
        store.append_actual_outcome(outcome)


@pytest.mark.parametrize("字段", ["market_time", "collected_at", "reference_price_available_at"])
def test_预测输入拒绝预测时点后才可得的市场或参考价格事实(字段: str) -> None:
    """预测不能引用预测时点后才到达的行情或参考价格。"""

    with pytest.raises(ValueError, match="预测时点|可得|市场|采集|参考"):
        _输入(**{字段: 时间 + timedelta(seconds=1)})


def test_预测输入拒绝未枚举的新鲜度值() -> None:
    """新鲜度必须使用受限枚举，未知字符串不能伪装为当前数据。"""

    with pytest.raises(ValueError, match="新鲜度|当前预测|freshness"):
        _输入(freshness="MAYBE_CURRENT")


def test_量化事实引用必须具有结构化工具审计锚点() -> None:
    """仅有自由文本和值哈希不足以证明数字来自本地或 MCP 工具。"""

    payload = _引用("up_probability").model_dump()
    for field in ("tool_name", "tool_version", "called_at", "data_as_of", "result_anchor"):
        payload.pop(field)
    with pytest.raises(ValidationError, match="Field required"):
        QuantitativeFactReference(**payload)


def test_快照追加拒绝输入输出证券版本和新鲜度不一致() -> None:
    """追加前必须绑定同一证券、版本与新鲜度，避免混合不同事实。"""

    store = PredictionSnapshotStore()
    with pytest.raises(ValueError, match="证券|版本|新鲜度"):
        store.append("snapshot-mismatch", _输入(), _输出(freshness="NEAR_REALTIME"))


def test_快照读取不能改写仓库内已保存的嵌套输出() -> None:
    """读取者修改返回对象不得污染追加保存的预测快照。"""

    store = PredictionSnapshotStore()
    returned = store.append("snapshot-copy", _输入(), _输出())
    returned.prediction_output.primary_evidence = ("错误覆盖",)
    later = store._snapshots["snapshot-copy"]
    assert later.prediction_output.primary_evidence == ("本地事实",)


@pytest.mark.parametrize(
    "reference_price, expiry_price",
    [(Decimal("0"), Decimal("101")), (Decimal("100"), Decimal("0"))],
)
def test_非正到期价格保持待验证而不参与除法(
    reference_price: Decimal, expiry_price: Decimal
) -> None:
    """零或负价格不可形成可审计收益率，必须安全保持待验证。"""

    outcome = resolve_actual_outcome(
        prediction_snapshot_id="snapshot-price",
        prediction_time=时间,
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=date(2026, 7, 15),
        trading_calendar=日历,
        trading_calendar_version="calendar-us-v1",
        reference_total_return_adjusted_price=reference_price,
        expiry_total_return_adjusted_price=expiry_price,
        expiry_price_available_at=时间 + timedelta(days=1),
        validated_at=时间 + timedelta(days=1),
        prediction_label_rule=规则,
    )
    assert outcome.status is ActualOutcomeStatus.PENDING_VALIDATION
