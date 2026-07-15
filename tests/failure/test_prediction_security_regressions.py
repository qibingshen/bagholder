"""覆盖 T050 独立审查发现的预测领域安全回归。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps

import pytest
from pydantic import ValidationError

from stock_agent.domain.market import InstrumentIdentity, Market
from stock_agent.domain.market_rules import TradingCalendar
from stock_agent.domain.prediction import (
    ActualOutcome,
    ActualOutcomeStatus,
    ImmutablePredictionSnapshotError,
    LocalFactIssuer,
    PredictionInput,
    PredictionLabel,
    PredictionLabelRule,
    PredictionLabelRuleError,
    PredictionOutput,
    PredictionSnapshotStore,
    QuantitativeFactReference,
    QuantitativeFieldEvidence,
    issue_local_outcome_fact,
    outcome_fact_value,
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
        "label_rule_available_at": 时间,
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
        market_time=时间,
        collected_at=时间,
        available_at=时间,
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


@pytest.mark.parametrize(
    ("日历", "规则", "错误"),
    [
        (None, None, "必须同时绑定"),
        (日历, None, "必须同时绑定"),
        (None, 规则, "必须同时绑定"),
        (
            TradingCalendar(
                market="CN",
                version_id="calendar-us-v1",
                trading_days=frozenset({date(2026, 7, 14), date(2026, 7, 15)}),
            ),
            规则,
            "市场必须与证券一致",
        ),
    ],
)
def test_快照追加必须绑定同市场日历与标签规则(
    日历: TradingCalendar | None, 规则: PredictionLabelRule | None, 错误: str
) -> None:
    """预测快照必须固定预测时采用的日历和规则，不能留空或跨市场混用。"""

    store = PredictionSnapshotStore()
    with pytest.raises(ImmutablePredictionSnapshotError, match=错误):
        store.append(
            "snapshot-required-anchors",
            _输入(),
            _输出(),
            trading_calendar=日历,
            prediction_label_rule=规则,
        )


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
    values = {
        "REFERENCE_PRICE": Decimal("100"),
        "EXPIRY_PRICE": Decimal("101"),
        "REFERENCE_TRADABILITY": "TRADABLE",
        "EXPIRY_TRADABILITY": "TRADABLE",
        "TRADING_CALENDAR": 日历,
        "LABEL_RULE": 规则,
        "COMPANY_ACTIONS": (),
    }
    versions = {
        "REFERENCE_PRICE": "daily-v1",
        "EXPIRY_PRICE": "daily-v1",
        "REFERENCE_TRADABILITY": "daily-v1",
        "EXPIRY_TRADABILITY": "daily-v1",
        "TRADING_CALENDAR": "calendar-us-v1",
        "LABEL_RULE": "label-v1",
        "COMPANY_ACTIONS": "company-actions-v1",
    }
    facts = tuple(
        issue_local_outcome_fact(
            fact_type=fact_type,
            security_id=证券,
            prediction_snapshot_id="snapshot-facts",
            prediction_time=时间,
            reference_type="LOCAL",
            source_id="local-history",
            tool_name="local_fact_store",
            tool_version="v1",
            market_time=(
                时间
                if fact_type == "REFERENCE_PRICE"
                else 时间 + timedelta(days=1)
                if fact_type == "EXPIRY_PRICE"
                else validated_at
            ),
            collected_at=(
                时间
                if fact_type == "REFERENCE_PRICE"
                else 时间 + timedelta(days=1)
                if fact_type == "EXPIRY_PRICE"
                else validated_at
            ),
            available_at=(
                时间
                if fact_type == "REFERENCE_PRICE"
                else 时间 + timedelta(days=1)
                if fact_type == "EXPIRY_PRICE"
                else validated_at
            ),
            version_id=versions[fact_type],
            result_id=f"result-{fact_type}",
            result_anchor=f"local://outcomes/result-{fact_type}",
            fact_value=outcome_fact_value(fact_type, values[fact_type]),
            value_hash=sha256(
                f"{fact_type}:{outcome_fact_value(fact_type, values[fact_type])}".encode()
            ).hexdigest(),
        )
        for fact_type in (
            "REFERENCE_PRICE",
            "EXPIRY_PRICE",
            "REFERENCE_TRADABILITY",
            "EXPIRY_TRADABILITY",
            "TRADING_CALENDAR",
            "LABEL_RULE",
            "COMPANY_ACTIONS",
        )
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
        security_id=证券,
        price_data_version="daily-v1",
    )
    assert outcome.status is ActualOutcomeStatus.VALIDATED
    assert outcome.fact_references == facts


def test_快照追加对调用方嵌套对象防御拷贝() -> None:
    store = PredictionSnapshotStore()
    预测输入 = _输入()
    预测输出 = _输出()
    snapshot = store.append(
        "snapshot-1",
        预测输入,
        预测输出,
        trading_calendar=日历,
        prediction_label_rule=规则,
    )
    预测输出.primary_evidence = ("被调用方修改",)
    assert snapshot.prediction_output.primary_evidence == ("本地事实",)


def test_结果追加拒绝非快照派生的预测时点() -> None:
    store = PredictionSnapshotStore()
    store.append("snapshot-1", _输入(), _输出(), trading_calendar=日历, prediction_label_rule=规则)
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


@pytest.mark.parametrize("字段", ["calendar_available_at", "label_rule_available_at"])
@pytest.mark.parametrize(
    "值",
    [None, datetime(2026, 7, 14, 9, 30)],
)
def test_预测输入要求日历和标签规则具有预测前的带时区可得时点(
    字段: str, 值: datetime | None
) -> None:
    """日历和标签规则都是预测事实，缺失或无时区时不能生成当前预测。"""

    with pytest.raises(ValueError, match="日历|规则|可得时点|时区"):
        _输入(**{字段: 值})


@pytest.mark.parametrize("字段", ["calendar_available_at", "label_rule_available_at"])
def test_预测输入拒绝预测时点后才可得的日历或标签规则(字段: str) -> None:
    """预测快照不得绑定预测产生后才可得的治理事实。"""

    with pytest.raises(ValueError, match="预测时点|日历|规则"):
        _输入(**{字段: 时间 + timedelta(seconds=1)})


@pytest.mark.parametrize("字段", ["calendar_available_at", "label_rule_available_at"])
def test_快照追加复验日历和标签规则的可得时点(字段: str) -> None:
    """调用方绕过输入构造时，追加入口仍须拒绝未来治理事实。"""

    store = PredictionSnapshotStore()
    unsafe_input = _输入().model_copy(update={字段: 时间 + timedelta(seconds=1)})

    with pytest.raises(ImmutablePredictionSnapshotError, match="日历|规则|可得时点|预测时点"):
        store.append(
            "snapshot-future-governance-fact",
            unsafe_input,
            _输出(),
            trading_calendar=日历,
            prediction_label_rule=规则,
        )


@pytest.mark.parametrize("阈值", [Decimal("NaN"), Decimal("Infinity")])
def test_标签规则拒绝非有限阈值(阈值: Decimal) -> None:
    """NaN 和无穷阈值不能参与历史标签分类。"""

    # Pydantic 会在领域规则前拒绝非有限 Decimal；两层均须视为安全拒绝。
    with pytest.raises((PredictionLabelRuleError, ValidationError)):
        PredictionLabelRule(
            version_id="invalid-label-rule",
            thresholds={1: 阈值, 5: Decimal("0.03"), 20: Decimal("0.06")},
        )


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
        store.append(
            "snapshot-mismatch",
            _输入(),
            _输出(freshness="NEAR_REALTIME"),
            trading_calendar=日历,
            prediction_label_rule=规则,
        )


def test_快照读取不能改写仓库内已保存的嵌套输出() -> None:
    """读取者修改返回对象不得污染追加保存的预测快照。"""

    store = PredictionSnapshotStore()
    returned = store.append(
        "snapshot-copy", _输入(), _输出(), trading_calendar=日历, prediction_label_rule=规则
    )
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


def _完整到期事实(
    *,
    snapshot_id: str,
    calendar: TradingCalendar = 日历,
    security: InstrumentIdentity = 证券,
    reference_market_time: datetime = 时间,
    expiry_market_time: datetime = 时间 + timedelta(days=1),
    include_tradability: bool = True,
    validated_at: datetime | None = None,
) -> tuple[object, ...]:
    """构造由内置本地审计服务签发的最小完整到期事实。"""

    validated_at = validated_at or 时间 + timedelta(days=2)
    values = {
        "REFERENCE_PRICE": Decimal("100"),
        "EXPIRY_PRICE": Decimal("101"),
        "TRADING_CALENDAR": calendar,
        "LABEL_RULE": 规则,
        "COMPANY_ACTIONS": (),
    }
    if include_tradability:
        values.update(
            {
                "REFERENCE_TRADABILITY": "TRADABLE",
                "EXPIRY_TRADABILITY": "TRADABLE",
            }
        )
    versions = {
        "REFERENCE_PRICE": "daily-v1",
        "EXPIRY_PRICE": "daily-v1",
        "TRADING_CALENDAR": calendar.version_id,
        "LABEL_RULE": "label-v1",
        "COMPANY_ACTIONS": "company-actions-v1",
        "REFERENCE_TRADABILITY": "daily-v1",
        "EXPIRY_TRADABILITY": "daily-v1",
    }
    return tuple(
        issue_local_outcome_fact(
            fact_type=fact_type,
            security_id=security,
            prediction_snapshot_id=snapshot_id,
            prediction_time=时间,
            reference_type="LOCAL",
            source_id="local-history",
            tool_name="local_fact_store",
            tool_version="v1",
            market_time=(
                reference_market_time
                if fact_type == "REFERENCE_PRICE"
                else expiry_market_time
                if fact_type == "EXPIRY_PRICE"
                else validated_at
            ),
            collected_at=(
                reference_market_time
                if fact_type == "REFERENCE_PRICE"
                else expiry_market_time
                if fact_type == "EXPIRY_PRICE"
                else validated_at
            ),
            available_at=(
                reference_market_time
                if fact_type == "REFERENCE_PRICE"
                else expiry_market_time
                if fact_type == "EXPIRY_PRICE"
                else validated_at
            ),
            version_id=versions[fact_type],
            result_id=f"result-{fact_type}",
            result_anchor=f"local://outcomes/result-{fact_type}",
            fact_value=outcome_fact_value(fact_type, values[fact_type]),
            value_hash=sha256(
                f"{fact_type}:{outcome_fact_value(fact_type, values[fact_type])}".encode()
            ).hexdigest(),
        )
        for fact_type in values
    )


def _已验证到期结果(*, snapshot_id: str, **overrides: object) -> ActualOutcome:
    """解析用于仓储门禁测试的有效到期结果。"""

    payload: dict[str, object] = {
        "prediction_snapshot_id": snapshot_id,
        "prediction_time": 时间,
        "horizon_trading_days": 1,
        "reference_trading_day": date(2026, 7, 14),
        "expiry_trading_day": date(2026, 7, 15),
        "trading_calendar": 日历,
        "trading_calendar_version": "calendar-us-v1",
        "reference_total_return_adjusted_price": Decimal("100"),
        "expiry_total_return_adjusted_price": Decimal("101"),
        "expiry_price_available_at": 时间 + timedelta(days=1),
        "validated_at": 时间 + timedelta(days=2),
        "prediction_label_rule": 规则,
        "outcome_fact_references": _完整到期事实(snapshot_id=snapshot_id),
        "security_id": 证券,
        "price_data_version": "daily-v1",
    }
    payload.update(overrides)
    return resolve_actual_outcome(**payload)


def test_到期日按证券市场本地日期判断而非_utc_日期() -> None:
    """美国市场在到期日当地收盘前不能因 UTC 已跨日而提前验证。"""

    验证时点 = datetime(2026, 7, 16, 1, 0, tzinfo=UTC)
    到期价格时点 = datetime(2026, 7, 15, 9, 30, tzinfo=UTC)
    outcome = _已验证到期结果(
        snapshot_id="snapshot-local-expiry-boundary",
        expiry_price_available_at=到期价格时点,
        validated_at=验证时点,
        outcome_fact_references=_完整到期事实(
            snapshot_id="snapshot-local-expiry-boundary",
            expiry_market_time=到期价格时点,
            validated_at=验证时点,
        ),
    )

    assert outcome.status is ActualOutcomeStatus.PENDING_VALIDATION


@pytest.mark.parametrize(
    ("security", "calendar", "价格可得时点", "到期事实时点", "预期状态"),
    [
        (
            证券,
            日历,
            datetime(2026, 7, 15, 0, 30, tzinfo=UTC),
            datetime(2026, 7, 15, 14, 0, tzinfo=UTC),
            ActualOutcomeStatus.PENDING_VALIDATION,
        ),
        (
            InstrumentIdentity(
                market=Market.HK, exchange="HKEX", display_code="00700", currency="HKD"
            ),
            TradingCalendar(
                market="HK",
                version_id="calendar-hk-v1",
                trading_days=frozenset({date(2026, 7, 14), date(2026, 7, 15)}),
            ),
            datetime(2026, 7, 14, 16, 30, tzinfo=UTC),
            datetime(2026, 7, 14, 16, 30, tzinfo=UTC),
            ActualOutcomeStatus.VALIDATED,
        ),
    ],
)
def test_到期价格可得性必须按证券市场日期判断(
    security: InstrumentIdentity,
    calendar: TradingCalendar,
    价格可得时点: datetime,
    到期事实时点: datetime,
    预期状态: ActualOutcomeStatus,
) -> None:
    """UTC 日期与当地交易日不一致时，不得误判价格已经或尚未可得。"""

    snapshot_id = f"snapshot-expiry-price-market-date-{security.market.value}"
    outcome = _已验证到期结果(
        snapshot_id=snapshot_id,
        trading_calendar=calendar,
        trading_calendar_version=calendar.version_id,
        expiry_price_available_at=价格可得时点,
        validated_at=datetime(2026, 7, 17, 0, 0, tzinfo=UTC),
        security_id=security,
        outcome_fact_references=_完整到期事实(
            snapshot_id=snapshot_id,
            calendar=calendar,
            security=security,
            expiry_market_time=到期事实时点,
            validated_at=datetime(2026, 7, 17, 0, 0, tzinfo=UTC),
        ),
    )

    assert outcome.status is 预期状态


def test_缺少两端可交易状态事实的结果不得验证() -> None:
    """价格齐全也不能替代参考日和到期日的可交易性事实。"""

    outcome = _已验证到期结果(
        snapshot_id="snapshot-tradability",
        outcome_fact_references=_完整到期事实(
            snapshot_id="snapshot-tradability", include_tradability=False
        ),
    )

    assert outcome.status is ActualOutcomeStatus.PENDING_VALIDATION


def test_仓储拒绝调用方伪造的已验证标签结果() -> None:
    """仓储入口必须重验事实和标签，不能信任调用方声称的 VALIDATED。"""

    store = PredictionSnapshotStore()
    store.append(
        "snapshot-direct", _输入(), _输出(), trading_calendar=日历, prediction_label_rule=规则
    )
    outcome = _已验证到期结果(snapshot_id="snapshot-direct")
    forged = ActualOutcome(
        **{**outcome.__dict__, "status": ActualOutcomeStatus.VALIDATED, "label": "UP"}
    )

    with pytest.raises(ImmutablePredictionSnapshotError, match="事实|标签|验证"):
        store.append_actual_outcome(forged)


def _替换已签名事实值(reference: object, *, fact_value: str) -> object:
    """保持签名有效，以验证仓储必须重建并校验事实中的结构化领域对象。"""

    payload = reference.model_dump(exclude={"issuer_id", "issuer_signature"})
    payload["security_id"] = reference.security_id
    return issue_local_outcome_fact(
        **{
            **payload,
            "fact_value": fact_value,
            "value_hash": sha256(f"{payload['fact_type']}:{fact_value}".encode()).hexdigest(),
        }
    )


@pytest.mark.parametrize(
    ("fact_type", "fact_value"),
    [
        (
            "TRADING_CALENDAR",
            '{"market":"US","trading_days":["2026-07-14","2026-07-15","2026-07-15"],"version_id":"calendar-us-v1"}',
        ),
        (
            "LABEL_RULE",
            '{"thresholds":{"1":"0.01","5":"0.03","20":"0.06","99":"0.09"},"version_id":"label-v1"}',
        ),
    ],
)
def test_仓储拒绝已签名但不能重建为有效领域对象的归一化事实(
    fact_type: str, fact_value: str
) -> None:
    """签名只证明来源，仓储仍须拒绝无效日历、规则和公司行动 JSON。"""

    store = PredictionSnapshotStore()
    store.append(
        "snapshot-normalization",
        _输入(),
        _输出(),
        trading_calendar=日历,
        prediction_label_rule=规则,
    )
    outcome = _已验证到期结果(snapshot_id="snapshot-normalization")
    forged_facts = tuple(
        _替换已签名事实值(reference, fact_value=fact_value)
        if reference.fact_type == fact_type
        else reference
        for reference in outcome.fact_references
    )
    forged = ActualOutcome(**{**outcome.__dict__, "fact_references": forged_facts})

    with pytest.raises(ImmutablePredictionSnapshotError, match="事实|标签|验证"):
        store.append_actual_outcome(forged)


def test_仓储拒绝已签名但复权比例非法的公司行动事实() -> None:
    """公司行动必须完整重建，不能只校验证券和时点等少数字段。"""

    store = PredictionSnapshotStore()
    store.append(
        "snapshot-action-normalization",
        _输入(),
        _输出(),
        trading_calendar=日历,
        prediction_label_rule=规则,
    )
    outcome = _已验证到期结果(snapshot_id="snapshot-action-normalization")
    invalid_actions = dumps(
        [
            {
                "action_id": "split-invalid",
                "action_type": "SPLIT",
                "effective_at": 时间.isoformat(),
                "available_at": None,
                "version_id": "actions-v1",
                "source_id": "local-history",
                "adjustment_ratio": "0",
                "security_id": str(证券),
                "market": "US",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    forged_facts = tuple(
        _替换已签名事实值(reference, fact_value=invalid_actions)
        if reference.fact_type == "COMPANY_ACTIONS"
        else reference
        for reference in outcome.fact_references
    )
    forged = ActualOutcome(**{**outcome.__dict__, "fact_references": forged_facts})

    with pytest.raises(ImmutablePredictionSnapshotError, match="事实|标签|验证"):
        store.append_actual_outcome(forged)


def test_仓储拒绝已签名的无穷价格事实() -> None:
    """即使来源签名有效，非有限价格也不能成为可持久化的到期结果。"""

    store = PredictionSnapshotStore()
    store.append(
        "snapshot-infinite-price",
        _输入(),
        _输出(),
        trading_calendar=日历,
        prediction_label_rule=规则,
    )
    outcome = _已验证到期结果(snapshot_id="snapshot-infinite-price")
    forged_facts = tuple(
        _替换已签名事实值(reference, fact_value="Infinity")
        if reference.fact_type == "REFERENCE_PRICE"
        else reference
        for reference in outcome.fact_references
    )
    forged = ActualOutcome(
        **{
            **outcome.__dict__,
            "reference_total_return_adjusted_price": Decimal("Infinity"),
            "label": PredictionLabel.DOWN,
            "fact_references": forged_facts,
        }
    )

    with pytest.raises(ImmutablePredictionSnapshotError, match="事实|标签|验证"):
        store.append_actual_outcome(forged)


@pytest.mark.parametrize(
    ("fact_type", "noncanonical_value"),
    [("REFERENCE_PRICE", "01.0"), ("EXPIRY_PRICE", "1.00")],
)
def test_仓储拒绝已签名但非规范编码的价格事实(fact_type: str, noncanonical_value: str) -> None:
    """价格事实必须与 Decimal 值的唯一规范文本逐字一致，不能只比较数值相等。"""

    store = PredictionSnapshotStore()
    store.append(
        "snapshot-price-normalization",
        _输入(),
        _输出(),
        trading_calendar=日历,
        prediction_label_rule=规则,
    )
    outcome = _已验证到期结果(snapshot_id="snapshot-price-normalization")
    forged_facts = tuple(
        _替换已签名事实值(reference, fact_value=noncanonical_value)
        if reference.fact_type == fact_type
        else _替换已签名事实值(reference, fact_value="1")
        if reference.fact_type in {"REFERENCE_PRICE", "EXPIRY_PRICE"}
        else reference
        for reference in outcome.fact_references
    )
    forged = ActualOutcome(
        **{
            **outcome.__dict__,
            "reference_total_return_adjusted_price": Decimal("1"),
            "expiry_total_return_adjusted_price": Decimal("1"),
            "label": PredictionLabel.FLAT,
            "fact_references": forged_facts,
        }
    )

    with pytest.raises(ImmutablePredictionSnapshotError, match="事实|标签|验证"):
        store.append_actual_outcome(forged)


@pytest.mark.parametrize(
    ("reference_market_time", "expiry_market_time"),
    [
        (时间 - timedelta(days=1), 时间 + timedelta(days=1)),
        (时间, 时间 + timedelta(days=2)),
    ],
)
def test_价格事实市场日期必须严格绑定参考日与到期日(
    reference_market_time: datetime, expiry_market_time: datetime
) -> None:
    """不允许以前后交易日的价格替代指定预测边界价格。"""

    outcome = _已验证到期结果(
        snapshot_id="snapshot-price-date",
        outcome_fact_references=_完整到期事实(
            snapshot_id="snapshot-price-date",
            reference_market_time=reference_market_time,
            expiry_market_time=expiry_market_time,
        ),
    )

    assert outcome.status is ActualOutcomeStatus.PENDING_VALIDATION


def test_解析器拒绝调用方注入未受信本地签发方() -> None:
    """签发方只能由应用受信注册表决定，调用方不得替换。"""

    with pytest.raises(TypeError):
        _已验证到期结果(
            snapshot_id="snapshot-untrusted-issuer",
            fact_issuer=LocalFactIssuer("attacker"),
        )


def _重签事实(reference: object, **overrides: object) -> object:
    """只为仓储边界测试重签受信事实，模拟受信服务的异常输入。"""

    payload = reference.model_dump(exclude={"issuer_id", "issuer_signature"})
    payload["security_id"] = reference.security_id
    payload.update(overrides)
    if "fact_value" in overrides:
        payload["value_hash"] = sha256(
            f"{payload['fact_type']}:{payload['fact_value']}".encode()
        ).hexdigest()
    return issue_local_outcome_fact(**payload)


def test_仓储拒绝预测时点后才可得的参考价格事实() -> None:
    """受信签名不能把预测完成后才采集的价格伪装成历史参考价。"""

    store = PredictionSnapshotStore()
    store.append(
        "snapshot-reference-future",
        _输入(),
        _输出(),
        trading_calendar=日历,
        prediction_label_rule=规则,
    )
    outcome = _已验证到期结果(snapshot_id="snapshot-reference-future")
    future = 时间 + timedelta(minutes=1)
    forged_facts = tuple(
        _重签事实(
            reference,
            market_time=future,
            collected_at=future,
            available_at=future,
        )
        if reference.fact_type == "REFERENCE_PRICE"
        else reference
        for reference in outcome.fact_references
    )
    forged = ActualOutcome(**{**outcome.__dict__, "fact_references": forged_facts})

    with pytest.raises(ImmutablePredictionSnapshotError, match="事实|标签|验证"):
        store.append_actual_outcome(forged)


def test_仓储拒绝到期交易日尚未结束的已验证结果() -> None:
    """验证日必须严格晚于到期交易日，不能在到期日盘中提前落库。"""

    store = PredictionSnapshotStore()
    store.append(
        "snapshot-expiry-early", _输入(), _输出(), trading_calendar=日历, prediction_label_rule=规则
    )
    outcome = _已验证到期结果(snapshot_id="snapshot-expiry-early")
    early = 时间 + timedelta(days=1)
    forged_facts = tuple(
        _重签事实(
            reference,
            market_time=early if reference.fact_type != "REFERENCE_PRICE" else 时间,
            collected_at=early if reference.fact_type != "REFERENCE_PRICE" else 时间,
            available_at=early if reference.fact_type != "REFERENCE_PRICE" else 时间,
        )
        for reference in outcome.fact_references
    )
    forged = ActualOutcome(
        **{**outcome.__dict__, "validated_at": early, "fact_references": forged_facts}
    )

    with pytest.raises(ImmutablePredictionSnapshotError, match="事实|标签|验证"):
        store.append_actual_outcome(forged)


def test_仓储拒绝已签名但非规范比例编码的公司行动事实() -> None:
    """比例文本也是审计事实，数值相等不能替代唯一规范编码。"""

    store = PredictionSnapshotStore()
    store.append(
        "snapshot-action-decimal",
        _输入(),
        _输出(),
        trading_calendar=日历,
        prediction_label_rule=规则,
    )
    outcome = _已验证到期结果(snapshot_id="snapshot-action-decimal")
    actions = dumps(
        [
            {
                "action_id": "split-canonical",
                "action_type": "SPLIT",
                "effective_at": 时间.isoformat(),
                "available_at": None,
                "version_id": "actions-v1",
                "source_id": "local-history",
                "adjustment_ratio": "1.0",
                "security_id": str(证券),
                "market": "US",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    forged_facts = tuple(
        _替换已签名事实值(reference, fact_value=actions)
        if reference.fact_type == "COMPANY_ACTIONS"
        else reference
        for reference in outcome.fact_references
    )
    forged = ActualOutcome(**{**outcome.__dict__, "fact_references": forged_facts})

    with pytest.raises(ImmutablePredictionSnapshotError, match="事实|标签|验证"):
        store.append_actual_outcome(forged)


def test_快照以内容摘要拒绝同版本日历替换() -> None:
    """版本标识相同不代表内容相同；快照必须绑定预测时采用的日历内容。"""

    store = PredictionSnapshotStore()
    snapshot = store.append(
        "snapshot-calendar-anchor",
        _输入(),
        _输出(),
        trading_calendar=日历,
        prediction_label_rule=规则,
    )
    altered_calendar = TradingCalendar(
        market="US",
        version_id="calendar-us-v1",
        trading_days=frozenset({date(2026, 7, 14), date(2026, 7, 15), date(2026, 7, 16)}),
    )
    resolved = resolve_actual_outcome(
        prediction_snapshot_id="snapshot-calendar-anchor",
        prediction_time=时间,
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=date(2026, 7, 15),
        trading_calendar=altered_calendar,
        trading_calendar_version="calendar-us-v1",
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=Decimal("101"),
        expiry_price_available_at=时间 + timedelta(days=1),
        validated_at=时间 + timedelta(days=2),
        prediction_label_rule=规则,
        snapshot_trading_calendar_version="calendar-us-v1",
        snapshot_trading_calendar_fact_value=snapshot.trading_calendar_fact_value,
        snapshot_label_rule_version="label-v1",
        snapshot_label_rule_fact_value=snapshot.label_rule_fact_value,
        outcome_fact_references=_完整到期事实(
            snapshot_id="snapshot-calendar-anchor", calendar=altered_calendar
        ),
        security_id=证券,
        price_data_version="daily-v1",
    )

    assert resolved.status is ActualOutcomeStatus.PENDING_VALIDATION


def test_快照以内容摘要拒绝同版本规则替换() -> None:
    """同名规则阈值被改写时，到期解析不能沿用预测快照的版本名。"""

    store = PredictionSnapshotStore()
    snapshot = store.append(
        "snapshot-rule-anchor",
        _输入(),
        _输出(),
        trading_calendar=日历,
        prediction_label_rule=规则,
    )
    altered_rule = PredictionLabelRule(
        version_id="label-v1",
        thresholds={1: Decimal("0.02"), 5: Decimal("0.03"), 20: Decimal("0.06")},
    )
    resolved = resolve_actual_outcome(
        prediction_snapshot_id="snapshot-rule-anchor",
        prediction_time=时间,
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=date(2026, 7, 15),
        trading_calendar=日历,
        trading_calendar_version="calendar-us-v1",
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=Decimal("101"),
        expiry_price_available_at=时间 + timedelta(days=1),
        validated_at=时间 + timedelta(days=2),
        prediction_label_rule=altered_rule,
        snapshot_trading_calendar_version="calendar-us-v1",
        snapshot_trading_calendar_fact_value=snapshot.trading_calendar_fact_value,
        snapshot_label_rule_version="label-v1",
        snapshot_label_rule_fact_value=snapshot.label_rule_fact_value,
        outcome_fact_references=_完整到期事实(snapshot_id="snapshot-rule-anchor"),
        security_id=证券,
        price_data_version="daily-v1",
    )

    assert resolved.status is ActualOutcomeStatus.PENDING_VALIDATION
