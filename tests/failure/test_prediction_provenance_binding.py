"""验证预测与到期事实引用必须绑定到实际输入，防止伪造审计记录。"""

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
    PredictionLabelRule,
    QuantitativeFactReference,
    QuantitativeFieldEvidence,
    quantitative_value_hash,
    resolve_actual_outcome,
)

预测时点 = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
证券 = InstrumentIdentity(market=Market.US, exchange="NASDAQ", display_code="AAPL", currency="USD")
日历 = TradingCalendar(
    market="US",
    version_id="calendar-us-v1",
    trading_days=frozenset({date(2026, 7, 14), date(2026, 7, 15)}),
)
规则 = PredictionLabelRule(
    version_id="label-v1", thresholds={1: Decimal("0.01"), 5: Decimal("0.03"), 20: Decimal("0.06")}
)


def _到期事实(事实类型: str, 值: str, 验证时点: datetime) -> OutcomeFactReference:
    return OutcomeFactReference(
        fact_type=事实类型,
        security_id=证券,
        prediction_snapshot_id="snapshot-1",
        prediction_time=预测时点,
        reference_type="LOCAL",
        source_id="local-history",
        tool_name="local_fact_store",
        tool_version="v1",
        market_time=验证时点,
        collected_at=验证时点,
        available_at=验证时点,
        version_id="daily-v1",
        result_id=f"result-{事实类型}",
        result_anchor=f"local://outcomes/result-{事实类型}",
        fact_value=值,
        value_hash=sha256(f"{事实类型}:{值}".encode()).hexdigest(),
    )


def test_到期价格事实与实际价格不一致时保持待验证() -> None:
    """自洽哈希不能替代与解析输入的逐值绑定。"""

    验证时点 = 预测时点 + timedelta(days=2)
    facts = (
        _到期事实("REFERENCE_PRICE", "999", 验证时点),
        _到期事实("EXPIRY_PRICE", "101", 验证时点),
        _到期事实("TRADING_CALENDAR", "任意日历", 验证时点),
        _到期事实("LABEL_RULE", "任意规则", 验证时点),
    )

    outcome = resolve_actual_outcome(
        prediction_snapshot_id="snapshot-1",
        prediction_time=预测时点,
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=date(2026, 7, 15),
        trading_calendar=日历,
        trading_calendar_version="calendar-us-v1",
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=Decimal("101"),
        expiry_price_available_at=验证时点,
        validated_at=验证时点,
        prediction_label_rule=规则,
        outcome_fact_references=facts,
        security_id=证券,
        price_data_version="daily-v1",
    )

    assert outcome.status is ActualOutcomeStatus.PENDING_VALIDATION
    assert outcome.fact_references == ()


def test_量化事实引用缺少独立市场采集和可得时点时拒绝() -> None:
    """预测数字必须分别保留市场、采集和可得时点，不能只写笼统数据时点。"""

    value = Decimal("40")
    with pytest.raises(ValidationError):
        QuantitativeFactReference(
            reference_type="LOCAL",
            result_id="fact-up",
            tool_name="local_fact_store",
            tool_version="v1",
            called_at=预测时点,
            data_as_of=预测时点,
            result_anchor="local://facts/fact-up",
            source_id="local-bars",
            security_id=证券,
            prediction_time=预测时点,
            data_version="daily-v1",
            feature_version="feature-v1",
            model_version="baseline-v1",
            label_rule_version="label-v1",
            covered_fields=("up_probability",),
            field_evidence=(
                QuantitativeFieldEvidence(
                    field_name="up_probability",
                    numeric_value=value,
                    value_hash=quantitative_value_hash("up_probability", value),
                    value_evidence="本地事实",
                ),
            ),
        )
