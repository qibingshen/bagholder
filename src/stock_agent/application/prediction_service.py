"""按预测时点事实生成简单基准预测快照的应用用例。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from stock_agent.domain.market import InstrumentIdentity
from stock_agent.domain.market_rules import TradingCalendar
from stock_agent.domain.prediction import (
    CurrentPredictionUnavailableError,
    Freshness,
    PredictionInput,
    PredictionLabelRule,
    PredictionSnapshot,
    PredictionSnapshotStore,
    QuantitativeFactReference,
    QuantitativeFieldEvidence,
    generate_simple_baseline_prediction,
    quantitative_value_hash,
)


class FeatureSnapshotFact(BaseModel):
    """预测时点已经可得的本地特征快照事实。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    snapshot_id: str = Field(min_length=1)
    security_id: InstrumentIdentity
    feature_version: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    market_time: datetime
    collected_at: datetime
    available_at: datetime
    cutoff_at: datetime
    values: dict[str, Decimal]

    @model_validator(mode="after")
    def validate_feature_fact(self) -> FeatureSnapshotFact:
        """特征事实必须有来源、时点顺序和有限数值。"""

        _require_aware(self.market_time, "特征市场时间")
        _require_aware(self.collected_at, "特征采集时间")
        _require_aware(self.available_at, "特征可得时间")
        _require_aware(self.cutoff_at, "特征截断时间")
        if not self.market_time <= self.collected_at <= self.available_at:
            raise CurrentPredictionUnavailableError("特征市场、采集和可得时间必须按顺序排列")
        if self.cutoff_at > self.available_at:
            raise CurrentPredictionUnavailableError("特征截断时间不得晚于特征可得时间")
        if not self.values or any(
            not name.strip() or not value.is_finite() for name, value in self.values.items()
        ):
            raise CurrentPredictionUnavailableError("特征快照必须包含可复核的有限数值")
        return self


class PredictionGenerationCommand(BaseModel):
    """生成当前简单基准预测所需的本地事实集合。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    security_id: InstrumentIdentity
    predicted_at: datetime
    market_time: datetime
    collected_at: datetime
    available_at: datetime | None = None
    source_id: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    horizon_trading_days: int
    freshness: Freshness
    reference_total_return_adjusted_price: Decimal | None = None
    reference_price_available_at: datetime | None = None
    trading_calendar: TradingCalendar
    calendar_available_at: datetime
    prediction_label_rule: PredictionLabelRule
    label_rule_available_at: datetime
    feature_snapshot: FeatureSnapshotFact
    primary_evidence: tuple[str, ...]
    risk_factors: tuple[str, ...]

    @model_validator(mode="after")
    def validate_generation_facts(self) -> PredictionGenerationCommand:
        """应用用例在进入领域模型前先收紧跨事实绑定关系。"""

        for value, label in (
            (self.predicted_at, "预测时点"),
            (self.market_time, "市场时间"),
            (self.collected_at, "采集时间"),
            (self.calendar_available_at, "日历可得时间"),
            (self.label_rule_available_at, "标签规则可得时间"),
        ):
            _require_aware(value, label)
        if self.available_at is not None:
            _require_aware(self.available_at, "数据可得时间")
        if self.reference_price_available_at is not None:
            _require_aware(self.reference_price_available_at, "参考价格可得时间")
        if self.trading_calendar.version_id == "":
            raise CurrentPredictionUnavailableError("交易日历版本不能为空")
        if self.trading_calendar.market != self.security_id.market.value:
            raise CurrentPredictionUnavailableError("交易日历市场必须与目标证券绑定")
        if self.feature_snapshot.security_id != self.security_id:
            raise CurrentPredictionUnavailableError("特征快照必须与目标证券绑定")
        if self.feature_snapshot.available_at > self.predicted_at:
            raise CurrentPredictionUnavailableError("特征在预测时点后才可得，存在未来数据风险")
        if self.feature_snapshot.cutoff_at > self.predicted_at:
            raise CurrentPredictionUnavailableError("特征截断时间晚于预测时点，存在未来数据风险")
        if self.calendar_available_at > self.predicted_at:
            raise CurrentPredictionUnavailableError("日历在预测时点后才可得")
        if self.label_rule_available_at > self.predicted_at:
            raise CurrentPredictionUnavailableError("标签规则在预测时点后才可得")
        return self


class PredictionService:
    """把本地事实转换为不可变预测快照，不训练模型、不发布模型、不连接交易。"""

    def __init__(self, *, snapshot_store: PredictionSnapshotStore) -> None:
        self._snapshot_store = snapshot_store

    def generate_simple_baseline_snapshot(
        self, command: PredictionGenerationCommand
    ) -> PredictionSnapshot:
        """生成指定周期的简单基准概率预测并追加保存快照。"""

        prediction_input = PredictionInput(
            security_id=command.security_id,
            predicted_at=command.predicted_at,
            market_time=command.market_time,
            collected_at=command.collected_at,
            available_at=command.available_at,
            source_id=command.source_id,
            data_version=command.data_version,
            feature_version=command.feature_snapshot.feature_version,
            trading_calendar_version=command.trading_calendar.version_id,
            calendar_available_at=command.calendar_available_at,
            label_rule_available_at=command.label_rule_available_at,
            feature_available_at=command.feature_snapshot.available_at,
            feature_cutoff_at=command.feature_snapshot.cutoff_at,
            model_version=command.model_version,
            prediction_label_rule_version=command.prediction_label_rule.version_id,
            freshness=command.freshness,
            time_is_verifiable=True,
            is_current_data_available=True,
            reference_total_return_adjusted_price=command.reference_total_return_adjusted_price,
            reference_price_available_at=command.reference_price_available_at,
        )
        quantitative_references = _baseline_quantitative_references(
            command=command,
            prediction_input=prediction_input,
        )
        prediction_output = generate_simple_baseline_prediction(
            prediction_input,
            horizon_trading_days=command.horizon_trading_days,
            primary_evidence=command.primary_evidence,
            risk_factors=command.risk_factors,
            quantitative_fact_references=quantitative_references,
        )
        return self._snapshot_store.append(
            _snapshot_id(command),
            prediction_input,
            prediction_output,
            trading_calendar=command.trading_calendar,
            prediction_label_rule=command.prediction_label_rule,
        )


def _baseline_quantitative_references(
    *,
    command: PredictionGenerationCommand,
    prediction_input: PredictionInput,
) -> tuple[QuantitativeFactReference, ...]:
    """为简单基准固定概率和置信度生成逐字段本地事实引用。"""

    values = {
        "up_probability": Decimal("34"),
        "flat_probability": Decimal("33"),
        "down_probability": Decimal("33"),
        "confidence": Decimal("0.5"),
    }
    return tuple(
        QuantitativeFactReference(
            reference_type="LOCAL",
            result_id=f"{command.feature_snapshot.snapshot_id}:{field_name}",
            tool_name="local_simple_baseline",
            tool_version="v1",
            called_at=command.predicted_at,
            data_as_of=command.feature_snapshot.available_at,
            market_time=command.feature_snapshot.market_time,
            collected_at=command.feature_snapshot.collected_at,
            available_at=command.feature_snapshot.available_at,
            result_anchor=f"local://predictions/{command.feature_snapshot.snapshot_id}/{field_name}",
            source_id=command.feature_snapshot.source_id,
            security_id=command.security_id,
            prediction_time=command.predicted_at,
            data_version=prediction_input.data_version,
            feature_version=prediction_input.feature_version,
            model_version=prediction_input.model_version,
            label_rule_version=prediction_input.prediction_label_rule_version or "",
            covered_fields=(field_name,),
            field_evidence=(
                QuantitativeFieldEvidence(
                    field_name=field_name,
                    numeric_value=value,
                    value_hash=quantitative_value_hash(field_name, value),
                    value_evidence="本地简单基准按固定三分类概率规则生成",
                ),
            ),
        )
        for field_name, value in values.items()
    )


def _snapshot_id(command: PredictionGenerationCommand) -> str:
    """生成稳定快照标识，避免同一证券同一预测时点同一周期被覆盖。"""

    market = command.security_id.market.value
    utc_text = command.predicted_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"prediction:{market}:{command.security_id.exchange}:"
        f"{command.security_id.display_code}:{utc_text}:{command.horizon_trading_days}d"
    )


def _require_aware(value: datetime, label: str) -> None:
    """所有应用层事实时间必须显式包含时区。"""

    if value.tzinfo is None or value.utcoffset() is None:
        raise CurrentPredictionUnavailableError(f"{label}必须包含时区")
