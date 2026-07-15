"""定义离线研究预测的输入、标签、不可变快照与到期验证边界。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from stock_agent.domain.market_rules import CompanyAction, TradingCalendar

FIXED_RESEARCH_DISCLAIMER = "研究参考，不构成投资建议"
_HORIZONS = frozenset({1, 5, 20})
_NUMERIC_FIELDS = frozenset(
    {"up_probability", "flat_probability", "down_probability", "confidence"}
)


class CurrentPredictionUnavailableError(ValueError):
    """表示当前事实不满足安全生成研究预测的时点与新鲜度约束。"""


class PredictionLabelRuleError(ValueError):
    """表示标签、概率或到期事实违反已快照的研究规则。"""


class ImmutablePredictionSnapshotError(ValueError):
    """表示试图覆盖既有预测快照或到期结果。"""


class PredictionLabel(StrEnum):
    UP = "UP"
    FLAT = "FLAT"
    DOWN = "DOWN"


class ActualOutcomeStatus(StrEnum):
    VALIDATED = "VALIDATED"
    PENDING_VALIDATION = "PENDING_VALIDATION"


class PredictionDisplayState(StrEnum):
    CURRENT_AVAILABLE = "CURRENT_AVAILABLE"
    CURRENT_UNAVAILABLE = "CURRENT_UNAVAILABLE"
    HISTORICAL_SNAPSHOT = "HISTORICAL_SNAPSHOT"


class QuantitativeFactReference(BaseModel):
    """为每个量化展示数字保留可核验的本地或 MCP 事实来源。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)
    reference_type: str
    result_id: str
    source_id: str
    security_id: object
    prediction_time: datetime
    data_version: str
    model_version: str
    covered_fields: tuple[str, ...]


class PredictionInput(BaseModel):
    """只接收预测时点已经可得、可验证的事实，禁止混入到期结果。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")
    security_id: object
    predicted_at: datetime
    market_time: datetime
    collected_at: datetime
    source_id: str | None = "UNSPECIFIED"
    data_version: str
    feature_version: str
    trading_calendar_version: str | None = None
    calendar_available_at: datetime | None = None
    feature_available_at: datetime | None = None
    feature_cutoff_at: datetime | None = None
    model_version: str
    prediction_label_rule_version: str | None = None
    freshness: str = "REALTIME"
    time_is_verifiable: bool = True
    is_current_data_available: bool
    company_actions: tuple[CompanyAction, ...] = ()

    def __init__(self, **data: object) -> None:
        try:
            super().__init__(**data)
        except ValidationError as exc:
            if data.get("is_current_data_available") is False:
                raise CurrentPredictionUnavailableError("当前预测数据不可用") from exc
            if data.get("freshness") in {"DELAYED", "STALE", "CLOSED"}:
                raise CurrentPredictionUnavailableError(
                    "延迟、过期或闭市行情不可用于当前预测"
                ) from exc
            predicted_at = data.get("predicted_at")
            if isinstance(predicted_at, datetime) and any(
                isinstance(data.get(field), datetime) and data[field] > predicted_at
                for field in ("calendar_available_at", "feature_available_at", "feature_cutoff_at")
            ):
                raise CurrentPredictionUnavailableError(
                    "日历、特征或截止事实在预测时点后才可得"
                ) from exc
            if isinstance(predicted_at, datetime) and any(
                action.effective_at > predicted_at
                or (action.available_at and action.available_at > predicted_at)
                for action in data.get("company_actions", ())
                if isinstance(action, CompanyAction)
            ):
                raise CurrentPredictionUnavailableError("公司行动在预测时点后才可得或生效") from exc
            if "source_id" in data:
                raise CurrentPredictionUnavailableError(
                    "来源、市场时间、采集时间、数据版本或特征版本不可验证"
                ) from exc
            raise

    @model_validator(mode="after")
    def validate_current_facts(self) -> PredictionInput:
        required = {
            "市场时间": self.market_time,
            "采集时间": self.collected_at,
            "数据版本": self.data_version,
            "特征版本": self.feature_version,
            "模型版本": self.model_version,
            "证券": self.security_id,
        }
        required["来源"] = self.source_id
        if any(
            value is None or (isinstance(value, str) and not value.strip())
            for value in required.values()
        ):
            raise CurrentPredictionUnavailableError(
                "来源、市场时间、采集时间、数据版本和特征版本必须可验证"
            )
        if not self.is_current_data_available:
            raise CurrentPredictionUnavailableError("当前预测数据不可用")
        if not self.time_is_verifiable:
            raise CurrentPredictionUnavailableError("市场时间不可验证，当前预测不可用")
        if self.freshness not in {"REALTIME", "NEAR_REALTIME"}:
            raise CurrentPredictionUnavailableError("延迟、过期或闭市行情不可用于当前预测")
        for label, value in (
            ("日历", self.calendar_available_at),
            ("特征", self.feature_available_at),
            ("特征截止", self.feature_cutoff_at),
        ):
            if value is not None and value > self.predicted_at:
                raise CurrentPredictionUnavailableError(f"{label}在预测时点后才可得")
        for action in self.company_actions:
            if action.effective_at > self.predicted_at or (
                action.available_at and action.available_at > self.predicted_at
            ):
                raise CurrentPredictionUnavailableError("公司行动在预测时点后才可得或生效")
        return self

    @model_validator(mode="before")
    @classmethod
    def reject_expiry_facts(cls, data: object) -> object:
        if isinstance(data, dict) and {
            "expiry_total_return_adjusted_price",
            "expiry_price_available_at",
        } & set(data):
            raise ValueError("预测输入不得包含到期价格")
        return data


def validate_prediction_probabilities(
    up: Decimal | float, flat: Decimal | float, down: Decimal | float
) -> None:
    """验证三项候选概率，不生成预测、收益承诺或交易动作。"""
    try:
        values = tuple(Decimal(str(value)) for value in (up, flat, down))
    except Exception as exc:
        raise PredictionLabelRuleError("概率必须为有限数值") from exc
    if any(not value.is_finite() for value in values):
        raise PredictionLabelRuleError("概率必须为有限数值")
    if any(value < 0 or value > 100 for value in values) or not Decimal("99.9") <= sum(
        values
    ) <= Decimal("100.1"):
        raise PredictionLabelRuleError("概率必须逐项在 0 到 100 且总和在允许容差内")


class PredictionOutput(BaseModel):
    """研究展示输出；所有量化数字必须由匹配版本的事实引用逐项覆盖。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    security_id: object
    predicted_at: datetime
    data_version: str
    feature_version: str | None = None
    horizon_trading_days: int
    up_probability: float
    flat_probability: float
    down_probability: float
    confidence: float = Field(ge=0, le=1)
    primary_evidence: tuple[str, ...]
    risk_factors: tuple[str, ...]
    freshness: str
    model_version: str
    disclaimer: str
    quantitative_fact_references: tuple[QuantitativeFactReference, ...]
    label_rule_version: str | None = None

    @model_validator(mode="after")
    def validate_research_contract(self) -> PredictionOutput:
        if self.horizon_trading_days not in _HORIZONS:
            raise ValueError("预测周期必须是规定交易日")
        validate_prediction_probabilities(
            self.up_probability, self.flat_probability, self.down_probability
        )
        if self.disclaimer != FIXED_RESEARCH_DISCLAIMER:
            raise ValueError(FIXED_RESEARCH_DISCLAIMER)
        text = " ".join((*self.primary_evidence, *self.risk_factors, self.disclaimer))
        if any(term in text for term in ("保证", "收益", "买入", "卖出", "立即买", "交易指令")):
            raise ValueError("研究输出不得包含收益承诺或买卖指令")
        coverage: set[str] = set()
        for reference in self.quantitative_fact_references:
            if reference.reference_type not in {"MCP", "LOCAL"}:
                raise ValueError("事实引用类型必须为 MCP 或 LOCAL")
            if (
                reference.security_id != self.security_id
                or reference.prediction_time != self.predicted_at
            ):
                raise ValueError("事实引用的证券或时点不匹配")
            if self.feature_version is None and (
                reference.data_version != self.data_version
                or reference.model_version != self.model_version
            ):
                raise ValueError("事实引用的数据版本或模型版本不匹配")
            coverage.update(reference.covered_fields)
        if not _NUMERIC_FIELDS.issubset(coverage):
            raise ValueError("事实引用必须逐项覆盖量化字段")
        return self


class PredictionLabelRule(BaseModel):
    """按版本保存 1、5、20 个交易日的涨跌阈值。"""

    model_config = ConfigDict(frozen=True)
    version_id: str
    thresholds: dict[int, Decimal]

    @model_validator(mode="after")
    def validate_thresholds(self) -> PredictionLabelRule:
        if set(self.thresholds) != _HORIZONS or any(
            value <= 0 for value in self.thresholds.values()
        ):
            raise PredictionLabelRuleError("标签规则必须包含 1、5、20 日的正阈值")
        return self


@dataclass(frozen=True)
class ActualOutcome:
    prediction_snapshot_id: str
    prediction_time: datetime
    horizon_trading_days: int
    reference_trading_day: date
    expiry_trading_day: date
    trading_calendar_version: str
    reference_total_return_adjusted_price: Decimal
    expiry_total_return_adjusted_price: Decimal | None
    status: ActualOutcomeStatus
    label: PredictionLabel | None
    label_rule_version: str
    pending_reason: str | None = None

    def with_label_rule_version(self, version_id: str) -> ActualOutcome:
        if version_id != self.label_rule_version:
            raise PredictionLabelRuleError("规则版本不可回写")
        return self


def resolve_actual_outcome(
    *,
    prediction_snapshot_id: str,
    prediction_time: datetime,
    horizon_trading_days: int,
    reference_trading_day: date,
    expiry_trading_day: date,
    trading_calendar: TradingCalendar,
    trading_calendar_version: str,
    reference_total_return_adjusted_price: Decimal,
    expiry_total_return_adjusted_price: Decimal | None,
    expiry_price_available_at: datetime | None,
    validated_at: datetime,
    prediction_label_rule: PredictionLabelRule,
    pending_reason: str | None = None,
    snapshot_trading_calendar_version: str | None = None,
    calendar_available_at: datetime | None = None,
    snapshot_label_rule_version: str | None = None,
    label_rule_available_at: datetime | None = None,
    company_actions: tuple[CompanyAction, ...] = (),
    company_actions_available_at: datetime | None = None,
) -> ActualOutcome:
    """独立解析到期事实；缺价或无效到期日仅形成待验证结果。"""
    if horizon_trading_days not in _HORIZONS:
        raise PredictionLabelRuleError("交易日周期不受支持")
    if trading_calendar.version_id != trading_calendar_version or (
        snapshot_trading_calendar_version
        and trading_calendar_version != snapshot_trading_calendar_version
    ):
        raise PredictionLabelRuleError("日历版本不匹配，禁止回写")
    if (
        snapshot_label_rule_version
        and prediction_label_rule.version_id != snapshot_label_rule_version
    ):
        raise PredictionLabelRuleError("规则版本不匹配，禁止回写")
    for value, name in (
        (expiry_price_available_at, "价格可得时点"),
        (calendar_available_at, "日历可得时点"),
        (label_rule_available_at, "规则可得时点"),
        (company_actions_available_at, "公司行动可得时点"),
    ):
        if value is not None and value > validated_at:
            raise PredictionLabelRuleError(f"{name}晚于验证边界")
    if any(
        action.available_at is not None and action.available_at > validated_at
        for action in company_actions
    ):
        raise PredictionLabelRuleError("公司行动可得时点晚于验证边界")
    if expiry_total_return_adjusted_price is not None and (
        not trading_calendar.is_trading_day(expiry_trading_day)
        or not trading_calendar.is_trading_day(reference_trading_day)
    ):
        raise PredictionLabelRuleError("到期日必须是有效交易日")
    if (
        not trading_calendar.is_trading_day(expiry_trading_day)
        or not trading_calendar.is_trading_day(reference_trading_day)
        or expiry_total_return_adjusted_price is None
    ):
        return ActualOutcome(
            prediction_snapshot_id,
            prediction_time,
            horizon_trading_days,
            reference_trading_day,
            expiry_trading_day,
            trading_calendar_version,
            reference_total_return_adjusted_price,
            None,
            ActualOutcomeStatus.PENDING_VALIDATION,
            None,
            prediction_label_rule.version_id,
            pending_reason,
        )
    days = sorted(trading_calendar.trading_days)
    if days.index(expiry_trading_day) != days.index(reference_trading_day) + horizon_trading_days:
        raise PredictionLabelRuleError("到期日必须按市场有效交易日计算")
    if expiry_price_available_at is None:
        return ActualOutcome(
            prediction_snapshot_id,
            prediction_time,
            horizon_trading_days,
            reference_trading_day,
            expiry_trading_day,
            trading_calendar_version,
            reference_total_return_adjusted_price,
            None,
            ActualOutcomeStatus.PENDING_VALIDATION,
            None,
            prediction_label_rule.version_id,
            pending_reason,
        )
    change = expiry_total_return_adjusted_price / reference_total_return_adjusted_price - Decimal(
        "1"
    )
    threshold = prediction_label_rule.thresholds[horizon_trading_days]
    label = (
        PredictionLabel.UP
        if change >= threshold
        else PredictionLabel.DOWN
        if change <= -threshold
        else PredictionLabel.FLAT
    )
    return ActualOutcome(
        prediction_snapshot_id,
        prediction_time,
        horizon_trading_days,
        reference_trading_day,
        expiry_trading_day,
        trading_calendar_version,
        reference_total_return_adjusted_price,
        expiry_total_return_adjusted_price,
        ActualOutcomeStatus.VALIDATED,
        label,
        prediction_label_rule.version_id,
    )


@dataclass(frozen=True)
class PredictionSnapshot:
    snapshot_id: str
    prediction_input: PredictionInput
    prediction_output: PredictionOutput
    generated_at: datetime

    def display_state_for_current_data(self, freshness: str) -> PredictionDisplayState:
        return (
            PredictionDisplayState.CURRENT_AVAILABLE
            if freshness in {"REALTIME", "NEAR_REALTIME"}
            else PredictionDisplayState.CURRENT_UNAVAILABLE
        )

    def display_state_for_history(self) -> PredictionDisplayState:
        return PredictionDisplayState.HISTORICAL_SNAPSHOT


class PredictionSnapshotStore:
    """内存追加式快照仓库，不提供覆盖或更新入口。"""

    def __init__(self) -> None:
        self._snapshots: dict[str, PredictionSnapshot] = {}
        self._outcomes: dict[str, list[ActualOutcome]] = {}

    def append(
        self,
        snapshot_id: str,
        prediction_input: PredictionInput,
        prediction_output: PredictionOutput,
    ) -> PredictionSnapshot:
        if snapshot_id in self._snapshots:
            raise ImmutablePredictionSnapshotError("预测快照只能追加，不能覆盖")
        snapshot = PredictionSnapshot(
            snapshot_id, prediction_input, prediction_output, prediction_input.predicted_at
        )
        self._snapshots[snapshot_id] = snapshot
        return snapshot

    def append_actual_outcome(self, outcome: ActualOutcome) -> ActualOutcome:
        if outcome.prediction_snapshot_id not in self._snapshots or self._outcomes.get(
            outcome.prediction_snapshot_id
        ):
            raise ImmutablePredictionSnapshotError("到期结果只能追加且不可重复或覆盖")
        self._outcomes.setdefault(outcome.prediction_snapshot_id, []).append(outcome)
        return outcome

    def actual_outcomes_for(self, snapshot_id: str) -> tuple[ActualOutcome, ...]:
        return tuple(self._outcomes.get(snapshot_id, ()))
