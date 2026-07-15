"""定义离线研究预测的输入、标签、不可变快照与到期验证边界。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from json import dumps, loads
from secrets import token_bytes
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from stock_agent.domain.market import Market
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


class Freshness(StrEnum):
    """限定行情新鲜度，避免未知字符串被当作当前可用数据。"""

    REALTIME = "REALTIME"
    NEAR_REALTIME = "NEAR_REALTIME"
    DELAYED = "DELAYED"
    STALE = "STALE"
    CLOSED = "CLOSED"


class QuantitativeFactReference(BaseModel):
    """为每个量化展示数字保留可核验的本地或 MCP 事实来源。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)
    reference_type: Literal["MCP", "LOCAL"]
    result_id: str
    tool_name: str
    tool_version: str
    called_at: datetime
    data_as_of: datetime
    market_time: datetime
    collected_at: datetime
    available_at: datetime
    result_anchor: str
    source_id: str
    security_id: object
    prediction_time: datetime
    data_version: str
    feature_version: str
    model_version: str
    label_rule_version: str
    covered_fields: tuple[str, ...] = ()
    field_evidence: tuple[QuantitativeFieldEvidence, ...]

    @model_validator(mode="after")
    def validate_reference_identity(self) -> QuantitativeFactReference:
        if (
            any(
                not isinstance(value, str) or not value.strip() or value == "UNSPECIFIED"
                for value in (
                    self.result_id,
                    self.source_id,
                    self.data_version,
                    self.feature_version,
                    self.model_version,
                    self.label_rule_version,
                )
            )
            or self.security_id is None
        ):
            raise ValueError("事实引用必须包含非空且已指定的标识与版本")
        _require_aware(self.prediction_time, "事实引用预测时点")
        for value, name in (
            (self.market_time, "市场时点"),
            (self.collected_at, "采集时点"),
            (self.available_at, "可得时点"),
            (self.data_as_of, "数据时点"),
            (self.called_at, "工具调用时点"),
        ):
            _require_aware(value, name)
            if value > self.prediction_time:
                raise ValueError(f"{name}不得晚于预测时点")
        if not (
            self.market_time
            <= self.collected_at
            <= self.available_at
            <= self.data_as_of
            <= self.called_at
        ):
            raise ValueError("量化事实必须按市场、采集、可得、数据和调用时点排序")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.tool_name, self.tool_version, self.result_anchor)
        ):
            raise ValueError("事实引用必须包含工具、调用、数据时点和结果锚定")
        expected_anchor_prefix = "local://" if self.reference_type == "LOCAL" else "mcp://"
        if not self.result_anchor.startswith(expected_anchor_prefix):
            raise ValueError("事实引用结果锚定必须与 LOCAL/MCP 来源一致")
        if not self.field_evidence:
            raise ValueError("事实引用必须包含逐字段数值、哈希和值证据")
        return self


class QuantitativeFieldEvidence(BaseModel):
    """绑定一个展示数值及其可复核摘要，覆盖声明本身不能构成证据。"""

    model_config = ConfigDict(frozen=True)
    field_name: str
    numeric_value: Decimal
    value_hash: str
    value_evidence: str

    @model_validator(mode="after")
    def validate_value_evidence(self) -> QuantitativeFieldEvidence:
        if (
            not self.field_name.strip()
            or not self.value_evidence.strip()
            or not self.numeric_value.is_finite()
        ):
            raise ValueError("数值证据必须完整且为有限数")
        if self.value_hash != quantitative_value_hash(self.field_name, self.numeric_value):
            raise ValueError("数值证据哈希不匹配")
        return self


class OutcomeFactReference(BaseModel):
    """保存到期价格、行动、日历和规则的可审计 LOCAL/MCP 事实来源。"""

    model_config = ConfigDict(frozen=True)
    fact_type: Literal[
        "REFERENCE_PRICE",
        "EXPIRY_PRICE",
        "REFERENCE_TRADABILITY",
        "EXPIRY_TRADABILITY",
        "COMPANY_ACTIONS",
        "TRADING_CALENDAR",
        "LABEL_RULE",
    ]
    security_id: object
    prediction_snapshot_id: str
    prediction_time: datetime
    reference_type: Literal["MCP", "LOCAL"]
    source_id: str
    tool_name: str
    tool_version: str
    market_time: datetime
    collected_at: datetime
    available_at: datetime
    version_id: str
    result_id: str
    result_anchor: str
    fact_value: str
    value_hash: str
    issuer_id: str = ""
    issuer_signature: str = ""

    @model_validator(mode="after")
    def validate_outcome_fact(self) -> OutcomeFactReference:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.source_id,
                self.tool_name,
                self.tool_version,
                self.version_id,
                self.result_id,
                self.result_anchor,
                self.fact_value,
                self.value_hash,
            )
        ):
            raise ValueError("到期事实必须包含来源、工具、版本、结果锚定和值哈希")
        for value, name in (
            (self.market_time, "市场时点"),
            (self.collected_at, "采集时点"),
            (self.available_at, "可得时点"),
        ):
            _require_aware(value, name)
        _require_aware(self.prediction_time, "到期事实预测时点")
        if self.security_id is None or not self.prediction_snapshot_id.strip():
            raise ValueError("到期事实必须绑定目标证券和预测快照")
        if not self.market_time <= self.collected_at <= self.available_at:
            raise ValueError("到期事实必须按市场、采集和可得时点排序")
        expected = "local://" if self.reference_type == "LOCAL" else "mcp://"
        if not self.result_anchor.startswith(expected):
            raise ValueError("到期事实结果锚定必须与 LOCAL/MCP 来源一致")
        expected_hash = sha256(f"{self.fact_type}:{self.fact_value}".encode()).hexdigest()
        if self.value_hash != expected_hash:
            raise ValueError("到期事实值哈希不匹配")
        return self


class LocalFactIssuer:
    """签发本地审计事实，私钥不进入公共 DTO 或快照。"""

    def __init__(self, issuer_id: str, secret: bytes | None = None) -> None:
        if not issuer_id.strip():
            raise ValueError("事实签发方标识不能为空")
        self.issuer_id = issuer_id
        self._secret = secret or token_bytes(32)

    def signature_for(self, reference: OutcomeFactReference) -> str:
        """以完整事实内容计算不可由 DTO 中公开字段重建的签名。"""
        payload = reference.model_dump(exclude={"issuer_id", "issuer_signature"}, mode="json")
        canonical = dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hmac_new(self._secret, canonical.encode(), sha256).hexdigest()

    def issue(self, **payload: object) -> OutcomeFactReference:
        """签发不可变的结构化事实引用。"""
        unsigned = OutcomeFactReference(**payload, issuer_id=self.issuer_id)
        return unsigned.model_copy(update={"issuer_signature": self.signature_for(unsigned)})

    def verifies(self, reference: OutcomeFactReference) -> bool:
        """只接受由当前受信本地签发方产生且未被改写的事实。"""
        return (
            reference.issuer_id == self.issuer_id
            and bool(reference.issuer_signature)
            and compare_digest(reference.issuer_signature, self.signature_for(reference))
        )


_DEFAULT_FACT_ISSUER = LocalFactIssuer("local-audit-service")
_TRUSTED_FACT_ISSUERS = {_DEFAULT_FACT_ISSUER.issuer_id: _DEFAULT_FACT_ISSUER}


def issue_local_outcome_fact(**payload: object) -> OutcomeFactReference:
    """由内置本地审计服务签发离线事实；公共 DTO 自行构造默认不受信任。"""
    return _DEFAULT_FACT_ISSUER.issue(**payload)


def _is_trusted_outcome_fact(reference: OutcomeFactReference) -> bool:
    """仅应用配置中的受信签发方可为结果事实背书。"""

    issuer = _TRUSTED_FACT_ISSUERS.get(reference.issuer_id)
    return issuer is not None and issuer.verifies(reference)


def _canonical_decimal(value: Decimal) -> str:
    """以稳定文本绑定价格事实，避免同值的展示格式影响审计。"""
    return format(value.normalize(), "f")


def _calendar_fact_value(calendar: TradingCalendar) -> str:
    """为交易日历生成稳定摘要，防止同版本下替换日历内容。"""
    return dumps(
        {
            "market": calendar.market,
            "version_id": calendar.version_id,
            "trading_days": [day.isoformat() for day in sorted(calendar.trading_days)],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _label_rule_fact_value(rule: PredictionLabelRule) -> str:
    """为标签规则生成稳定摘要，防止复用版本名篡改阈值。"""
    return dumps(
        {
            "version_id": rule.version_id,
            "thresholds": {
                str(day): _canonical_decimal(value) for day, value in rule.thresholds.items()
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _company_actions_fact_value(actions: tuple[CompanyAction, ...]) -> str:
    """为行动集合生成稳定摘要，确保集合和每项行动都未被替换。"""
    return dumps(
        [
            {
                "action_id": action.action_id,
                "action_type": action.action_type,
                "effective_at": action.effective_at.isoformat(),
                "available_at": action.available_at.isoformat() if action.available_at else None,
                "version_id": action.version_id,
                "source_id": action.source_id,
                "adjustment_ratio": (
                    _canonical_decimal(action.adjustment_ratio)
                    if action.adjustment_ratio is not None
                    else None
                ),
                "security_id": str(action.security_id),
                "market": action.market.value if action.market else None,
            }
            for action in sorted(actions, key=lambda item: item.action_id)
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def outcome_fact_value(
    fact_type: str,
    value: Decimal | TradingCalendar | PredictionLabelRule | tuple[CompanyAction, ...],
) -> str:
    """构造到期事实的稳定值，供本地存储和 MCP 适配器写入审计引用。"""
    if fact_type in {"REFERENCE_PRICE", "EXPIRY_PRICE"} and isinstance(value, Decimal):
        return _canonical_decimal(value)
    if fact_type == "TRADING_CALENDAR" and isinstance(value, TradingCalendar):
        return _calendar_fact_value(value)
    if fact_type == "LABEL_RULE" and isinstance(value, PredictionLabelRule):
        return _label_rule_fact_value(value)
    if fact_type == "COMPANY_ACTIONS" and isinstance(value, tuple):
        return _company_actions_fact_value(value)
    if fact_type in {"REFERENCE_TRADABILITY", "EXPIRY_TRADABILITY"} and value == "TRADABLE":
        return "TRADABLE"
    raise ValueError("到期事实类型和值不匹配")


def quantitative_value_hash(field_name: str, value: Decimal | float) -> str:
    """返回稳定的字段值摘要，仅供验证本地或 MCP 事实的逐字段绑定。"""
    return sha256(f"{field_name}:{Decimal(str(value)).normalize()}".encode()).hexdigest()


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}必须带时区")


def _security_market(security_id: object) -> str | None:
    """从已校验证券身份或兼容的市场前缀取得目标市场。"""

    market = getattr(security_id, "market", None)
    if market is not None:
        return getattr(market, "value", market)
    if isinstance(security_id, str) and ":" in security_id:
        return security_id.split(":", maxsplit=1)[0]
    return None


def _market_date(value: datetime, security_id: object, fallback_market: str | None = None) -> date:
    """按证券所属市场时区取得事实交易日，禁止以执行机器日期替代。"""

    timezone = getattr(security_id, "market_timezone", None)
    market = _security_market(security_id) or fallback_market
    if not isinstance(timezone, str) or not timezone:
        timezone = {"CN": "Asia/Shanghai", "HK": "Asia/Hong_Kong", "US": "America/New_York"}.get(
            market or ""
        )
    if not timezone:
        raise ValueError("到期事实必须绑定具有市场时区的证券")
    return value.astimezone(ZoneInfo(timezone)).date()


def _rebuild_calendar_outcome_fact(
    fact_value: str, *, expected_market: str, expected_version: str
) -> TradingCalendar:
    """将日历事实重建为领域对象，并拒绝重复、乱序或非规范编码。"""

    payload = loads(fact_value)
    if not isinstance(payload, dict) or set(payload) != {"market", "version_id", "trading_days"}:
        raise ValueError("交易日历事实字段不完整")
    raw_days = payload["trading_days"]
    if not isinstance(raw_days, list) or not raw_days:
        raise ValueError("交易日历事实必须包含交易日列表")
    days = [date.fromisoformat(value) for value in raw_days]
    if days != sorted(days) or len(days) != len(set(days)):
        raise ValueError("交易日历事实不得重复或乱序")
    calendar = TradingCalendar(
        market=payload["market"], version_id=payload["version_id"], trading_days=frozenset(days)
    )
    if calendar.market != expected_market or calendar.version_id != expected_version:
        raise ValueError("交易日历事实与快照不匹配")
    if outcome_fact_value("TRADING_CALENDAR", calendar) != fact_value:
        raise ValueError("交易日历事实不是规范编码")
    return calendar


def _rebuild_label_rule_outcome_fact(
    fact_value: str, *, expected_version: str
) -> PredictionLabelRule:
    """将标签规则事实重建为领域对象，避免非完整或非正阈值绕过持久化。"""

    payload = loads(fact_value)
    if not isinstance(payload, dict) or set(payload) != {"version_id", "thresholds"}:
        raise ValueError("标签规则事实字段不完整")
    raw_thresholds = payload["thresholds"]
    if not isinstance(raw_thresholds, dict):
        raise ValueError("标签规则阈值必须为对象")
    thresholds = {int(horizon): Decimal(value) for horizon, value in raw_thresholds.items()}
    rule = PredictionLabelRule(version_id=payload["version_id"], thresholds=thresholds)
    if not all(value.is_finite() and value > 0 for value in rule.thresholds.values()):
        raise ValueError("标签规则阈值必须为有限正数")
    if rule.version_id != expected_version:
        raise ValueError("标签规则事实与快照不匹配")
    if outcome_fact_value("LABEL_RULE", rule) != fact_value:
        raise ValueError("标签规则事实不是规范编码")
    return rule


def _rebuild_company_actions_outcome_fact(
    fact_value: str,
    *,
    security_id: object,
    expected_market: str,
) -> tuple[CompanyAction, ...]:
    """以完整字段重建公司行动，禁止只凭自由 JSON 参与复权结果。"""

    payload = loads(fact_value)
    if not isinstance(payload, list):
        raise ValueError("公司行动事实必须为列表")
    actions = []
    for raw_action in payload:
        if not isinstance(raw_action, dict) or set(raw_action) != {
            "action_id",
            "action_type",
            "effective_at",
            "available_at",
            "version_id",
            "source_id",
            "adjustment_ratio",
            "security_id",
            "market",
        }:
            raise ValueError("公司行动事实字段不完整")
        if raw_action["security_id"] != str(security_id) or raw_action["market"] != expected_market:
            raise ValueError("公司行动事实与证券或市场不匹配")
        available_at = raw_action["available_at"]
        action = CompanyAction(
            action_id=raw_action["action_id"],
            action_type=raw_action["action_type"],
            effective_at=datetime.fromisoformat(raw_action["effective_at"]),
            available_at=(
                datetime.fromisoformat(available_at) if available_at is not None else None
            ),
            version_id=raw_action["version_id"],
            source_id=raw_action["source_id"],
            adjustment_ratio=(
                Decimal(raw_action["adjustment_ratio"])
                if raw_action["adjustment_ratio"] is not None
                else None
            ),
            security_id=security_id,
            market=Market(raw_action["market"]),
        )
        actions.append(action)
    if [action.action_id for action in actions] != sorted(action.action_id for action in actions):
        raise ValueError("公司行动事实必须按标识排序且不可重复")
    if len({action.action_id for action in actions}) != len(actions):
        raise ValueError("公司行动事实不得重复")
    rebuilt = tuple(actions)
    if outcome_fact_value("COMPANY_ACTIONS", rebuilt) != fact_value:
        raise ValueError("公司行动事实不是规范编码")
    return rebuilt


class PredictionInput(BaseModel):
    """只接收预测时点已经可得、可验证的事实，禁止混入到期结果。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")
    security_id: object
    predicted_at: datetime
    market_time: datetime
    collected_at: datetime
    available_at: datetime | None = None
    source_id: str | None = "UNSPECIFIED"
    data_version: str
    feature_version: str
    trading_calendar_version: str | None = None
    calendar_available_at: datetime | None = None
    feature_available_at: datetime | None = None
    feature_cutoff_at: datetime | None = None
    model_version: str
    prediction_label_rule_version: str | None = None
    freshness: Freshness = Freshness.REALTIME
    time_is_verifiable: bool = True
    is_current_data_available: bool
    company_actions: tuple[CompanyAction, ...] = ()
    reference_total_return_adjusted_price: Decimal | None = None
    reference_price_available_at: datetime | None = None

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
            if data.get("source_id") is None or data.get("source_id") == "UNSPECIFIED":
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
        if self.source_id == "UNSPECIFIED":
            raise CurrentPredictionUnavailableError("来源不得为 UNSPECIFIED")
        for name, value in (
            ("预测时点", self.predicted_at),
            ("市场时点", self.market_time),
            ("采集时点", self.collected_at),
        ):
            _require_aware(value, name)
            if name != "预测时点" and value > self.predicted_at:
                raise CurrentPredictionUnavailableError(f"{name}不得晚于预测时点")
        available_at = self.available_at or self.collected_at
        _require_aware(available_at, "可得时点")
        if not self.market_time <= self.collected_at <= available_at <= self.predicted_at:
            raise CurrentPredictionUnavailableError("市场、采集、可得与预测时点必须按顺序排列")
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
            if value is not None:
                _require_aware(value, f"{label}可得时点")
            if value is not None and value > self.predicted_at:
                raise CurrentPredictionUnavailableError(f"{label}在预测时点后才可得")
        for action in self.company_actions:
            if (
                action.security_id is None
                or action.market is None
                or action.security_id != self.security_id
            ):
                raise CurrentPredictionUnavailableError("公司行动必须绑定目标证券与市场")
            if action.effective_at > self.predicted_at or (
                action.available_at and action.available_at > self.predicted_at
            ):
                raise CurrentPredictionUnavailableError("公司行动在预测时点后才可得或生效")
        if self.reference_price_available_at is not None:
            _require_aware(self.reference_price_available_at, "参考价格可得时点")
            if self.reference_price_available_at > self.predicted_at:
                raise CurrentPredictionUnavailableError("参考价格可得时点不得晚于预测时点")
        if self.reference_total_return_adjusted_price is not None and (
            not self.reference_total_return_adjusted_price.is_finite()
            or self.reference_total_return_adjusted_price <= 0
        ):
            raise CurrentPredictionUnavailableError("参考价格必须为有限正数")
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
        _require_aware(self.predicted_at, "预测时点")
        if (
            not self.primary_evidence
            or not self.risk_factors
            or any(not item.strip() for item in (*self.primary_evidence, *self.risk_factors))
        ):
            raise ValueError("主要依据和风险因素必须非空")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.data_version,
                self.feature_version,
                self.model_version,
                self.label_rule_version,
            )
        ):
            raise ValueError("数据、特征、模型和规则版本必须非空")
        text = " ".join((*self.primary_evidence, *self.risk_factors, self.disclaimer))
        if any(term in text for term in ("保证", "收益", "买入", "卖出", "立即买", "交易指令")):
            raise ValueError("研究输出不得包含收益承诺或买卖指令")
        evidence_by_field: dict[str, QuantitativeFieldEvidence] = {}
        for reference in self.quantitative_fact_references:
            if reference.reference_type not in {"MCP", "LOCAL"}:
                raise ValueError("事实引用类型必须为 MCP 或 LOCAL")
            if (
                reference.security_id != self.security_id
                or reference.prediction_time != self.predicted_at
            ):
                raise ValueError("事实引用的证券或时点不匹配")
            if (
                reference.data_version != self.data_version
                or reference.feature_version != self.feature_version
                or reference.model_version != self.model_version
                or reference.label_rule_version != self.label_rule_version
            ):
                raise ValueError("事实引用的版本不匹配")
            for evidence in reference.field_evidence:
                if evidence.field_name in evidence_by_field:
                    raise ValueError("每个量化字段只能有一条绑定证据")
                evidence_by_field[evidence.field_name] = evidence
        for field_name in _NUMERIC_FIELDS:
            evidence = evidence_by_field.get(field_name)
            if evidence is None or evidence.numeric_value != Decimal(
                str(getattr(self, field_name))
            ):
                raise ValueError("事实引用必须逐字段绑定数值、哈希和值证据")
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
    validated_at: datetime
    pending_reason: str | None = None
    fact_references: tuple[OutcomeFactReference, ...] = ()

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
    snapshot_trading_calendar_fact_value: str | None = None,
    calendar_available_at: datetime | None = None,
    snapshot_label_rule_version: str | None = None,
    snapshot_label_rule_fact_value: str | None = None,
    label_rule_available_at: datetime | None = None,
    company_actions: tuple[CompanyAction, ...] = (),
    company_actions_available_at: datetime | None = None,
    outcome_fact_references: tuple[OutcomeFactReference, ...] = (),
    security_id: object | None = None,
    price_data_version: str | None = None,
) -> ActualOutcome:
    """独立解析到期事实；缺价或无效到期日仅形成待验证结果。"""
    for name, value in (("预测时点", prediction_time), ("验证时点", validated_at)):
        _require_aware(value, name)
    if horizon_trading_days not in _HORIZONS:
        raise PredictionLabelRuleError("交易日周期不受支持")
    if trading_calendar.version_id != trading_calendar_version or (
        snapshot_trading_calendar_version
        and trading_calendar_version != snapshot_trading_calendar_version
    ):
        return _pending_outcome(
            prediction_snapshot_id,
            prediction_time,
            horizon_trading_days,
            reference_trading_day,
            expiry_trading_day,
            trading_calendar_version,
            reference_total_return_adjusted_price,
            expiry_total_return_adjusted_price,
            prediction_label_rule.version_id,
            validated_at,
            pending_reason or "日历版本不匹配",
        )
    if (
        snapshot_label_rule_version
        and prediction_label_rule.version_id != snapshot_label_rule_version
    ):
        return _pending_outcome(
            prediction_snapshot_id,
            prediction_time,
            horizon_trading_days,
            reference_trading_day,
            expiry_trading_day,
            trading_calendar_version,
            reference_total_return_adjusted_price,
            expiry_total_return_adjusted_price,
            prediction_label_rule.version_id,
            validated_at,
            pending_reason or "规则版本不匹配",
        )
    if (
        snapshot_trading_calendar_fact_value is not None
        and outcome_fact_value("TRADING_CALENDAR", trading_calendar)
        != snapshot_trading_calendar_fact_value
    ):
        return _pending_outcome(
            prediction_snapshot_id,
            prediction_time,
            horizon_trading_days,
            reference_trading_day,
            expiry_trading_day,
            trading_calendar_version,
            reference_total_return_adjusted_price,
            expiry_total_return_adjusted_price,
            prediction_label_rule.version_id,
            validated_at,
            pending_reason or "日历内容与预测快照不匹配",
        )
    if (
        snapshot_label_rule_fact_value is not None
        and outcome_fact_value("LABEL_RULE", prediction_label_rule)
        != snapshot_label_rule_fact_value
    ):
        return _pending_outcome(
            prediction_snapshot_id,
            prediction_time,
            horizon_trading_days,
            reference_trading_day,
            expiry_trading_day,
            trading_calendar_version,
            reference_total_return_adjusted_price,
            expiry_total_return_adjusted_price,
            prediction_label_rule.version_id,
            validated_at,
            pending_reason or "规则内容与预测快照不匹配",
        )
    for value, name in (
        (expiry_price_available_at, "价格可得时点"),
        (calendar_available_at, "日历可得时点"),
        (label_rule_available_at, "规则可得时点"),
        (company_actions_available_at, "公司行动可得时点"),
    ):
        if value is not None and value > validated_at:
            return _pending_outcome(
                prediction_snapshot_id,
                prediction_time,
                horizon_trading_days,
                reference_trading_day,
                expiry_trading_day,
                trading_calendar_version,
                reference_total_return_adjusted_price,
                expiry_total_return_adjusted_price,
                prediction_label_rule.version_id,
                validated_at,
                pending_reason or f"{name}晚于验证边界",
            )
    if any(
        action.available_at is not None and action.available_at > validated_at
        for action in company_actions
    ):
        return _pending_outcome(
            prediction_snapshot_id,
            prediction_time,
            horizon_trading_days,
            reference_trading_day,
            expiry_trading_day,
            trading_calendar_version,
            reference_total_return_adjusted_price,
            expiry_total_return_adjusted_price,
            prediction_label_rule.version_id,
            validated_at,
            pending_reason or "公司行动可得时点晚于验证边界",
        )
    required_fact_types = {
        "REFERENCE_PRICE",
        "EXPIRY_PRICE",
        "REFERENCE_TRADABILITY",
        "EXPIRY_TRADABILITY",
        "TRADING_CALENDAR",
        "LABEL_RULE",
    }
    required_fact_types.add("COMPANY_ACTIONS")
    provided_fact_types = {reference.fact_type for reference in outcome_fact_references}
    facts_by_type = {reference.fact_type: reference for reference in outcome_fact_references}
    facts_are_bound = (
        security_id is not None
        and bool(price_data_version)
        and len(facts_by_type) == len(outcome_fact_references)
        and all(
            reference.security_id == security_id
            and reference.prediction_snapshot_id == prediction_snapshot_id
            and reference.prediction_time == prediction_time
            and reference.available_at <= validated_at
            for reference in outcome_fact_references
        )
        and all(_is_trusted_outcome_fact(reference) for reference in outcome_fact_references)
        and facts_by_type.get("REFERENCE_PRICE") is not None
        and facts_by_type.get("EXPIRY_PRICE") is not None
        and facts_by_type.get("TRADING_CALENDAR") is not None
        and facts_by_type.get("LABEL_RULE") is not None
        and facts_by_type["REFERENCE_PRICE"].version_id == price_data_version
        and facts_by_type["EXPIRY_PRICE"].version_id == price_data_version
        and facts_by_type["REFERENCE_PRICE"].fact_value
        == outcome_fact_value("REFERENCE_PRICE", reference_total_return_adjusted_price)
        and expiry_total_return_adjusted_price is not None
        and facts_by_type["EXPIRY_PRICE"].fact_value
        == outcome_fact_value("EXPIRY_PRICE", expiry_total_return_adjusted_price)
        and facts_by_type.get("REFERENCE_TRADABILITY") is not None
        and facts_by_type.get("EXPIRY_TRADABILITY") is not None
        and facts_by_type["REFERENCE_TRADABILITY"].fact_value == "TRADABLE"
        and facts_by_type["EXPIRY_TRADABILITY"].fact_value == "TRADABLE"
        and facts_by_type["TRADING_CALENDAR"].version_id == trading_calendar.version_id
        and facts_by_type["TRADING_CALENDAR"].fact_value
        == outcome_fact_value("TRADING_CALENDAR", trading_calendar)
        and facts_by_type["LABEL_RULE"].version_id == prediction_label_rule.version_id
        and facts_by_type["LABEL_RULE"].fact_value
        == outcome_fact_value("LABEL_RULE", prediction_label_rule)
        and facts_by_type.get("COMPANY_ACTIONS") is not None
        and facts_by_type["COMPANY_ACTIONS"].fact_value
        == outcome_fact_value("COMPANY_ACTIONS", company_actions)
        and _security_market(security_id) is not None
        and trading_calendar.market == _security_market(security_id)
        and all(
            action.security_id == security_id
            and action.market == security_id.market
            and action.effective_at <= validated_at
            and (action.available_at is None or action.available_at <= validated_at)
            for action in company_actions
        )
    )
    if (
        not trading_calendar.is_trading_day(expiry_trading_day)
        or not trading_calendar.is_trading_day(reference_trading_day)
        or expiry_total_return_adjusted_price is None
        or expiry_price_available_at is None
        or validated_at.date() <= expiry_trading_day
        or expiry_price_available_at is not None
        and expiry_price_available_at.date() < expiry_trading_day
        or any(
            reference.fact_type == "REFERENCE_PRICE"
            and (
                reference.market_time > prediction_time or reference.available_at > prediction_time
            )
            for reference in outcome_fact_references
        )
        or any(
            reference.fact_type == "EXPIRY_PRICE"
            and _market_date(reference.market_time, security_id, trading_calendar.market)
            != expiry_trading_day
            for reference in outcome_fact_references
        )
        or any(
            reference.fact_type == "REFERENCE_PRICE"
            and _market_date(reference.market_time, security_id, trading_calendar.market)
            != reference_trading_day
            for reference in outcome_fact_references
        )
        or not required_fact_types.issubset(provided_fact_types)
        or not facts_are_bound
        or not reference_total_return_adjusted_price.is_finite()
        or reference_total_return_adjusted_price <= 0
        or (
            expiry_total_return_adjusted_price is not None
            and (
                not expiry_total_return_adjusted_price.is_finite()
                or expiry_total_return_adjusted_price <= 0
            )
        )
    ):
        return _pending_outcome(
            prediction_snapshot_id,
            prediction_time,
            horizon_trading_days,
            reference_trading_day,
            expiry_trading_day,
            trading_calendar_version,
            reference_total_return_adjusted_price,
            expiry_total_return_adjusted_price,
            prediction_label_rule.version_id,
            validated_at,
            pending_reason,
        )
    days = sorted(trading_calendar.trading_days)
    if days.index(expiry_trading_day) != days.index(reference_trading_day) + horizon_trading_days:
        return _pending_outcome(
            prediction_snapshot_id,
            prediction_time,
            horizon_trading_days,
            reference_trading_day,
            expiry_trading_day,
            trading_calendar_version,
            reference_total_return_adjusted_price,
            expiry_total_return_adjusted_price,
            prediction_label_rule.version_id,
            validated_at,
            pending_reason or "到期日不符合市场交易日历",
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
        validated_at,
        None,
        tuple(outcome_fact_references),
    )


def _pending_outcome(
    prediction_snapshot_id: str,
    prediction_time: datetime,
    horizon_trading_days: int,
    reference_trading_day: date,
    expiry_trading_day: date,
    trading_calendar_version: str,
    reference_price: Decimal,
    expiry_price: Decimal | None,
    label_rule_version: str,
    validated_at: datetime,
    pending_reason: str | None,
) -> ActualOutcome:
    """任何不可验证、不成交或链路不完整的情况只形成不可持久化的待验证结果。"""
    return ActualOutcome(
        prediction_snapshot_id,
        prediction_time,
        horizon_trading_days,
        reference_trading_day,
        expiry_trading_day,
        trading_calendar_version,
        reference_price,
        expiry_price,
        ActualOutcomeStatus.PENDING_VALIDATION,
        None,
        label_rule_version,
        validated_at,
        pending_reason,
        (),
    )


@dataclass(frozen=True)
class PredictionSnapshot:
    snapshot_id: str
    prediction_input: PredictionInput
    prediction_output: PredictionOutput
    generated_at: datetime
    trading_calendar_fact_value: str | None = None
    label_rule_fact_value: str | None = None

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
        *,
        trading_calendar: TradingCalendar | None = None,
        prediction_label_rule: PredictionLabelRule | None = None,
    ) -> PredictionSnapshot:
        if snapshot_id in self._snapshots:
            raise ImmutablePredictionSnapshotError("预测快照只能追加，不能覆盖")
        if prediction_input.predicted_at != prediction_output.predicted_at:
            raise ImmutablePredictionSnapshotError("快照输入输出预测时点必须一致")
        if prediction_input.security_id != prediction_output.security_id:
            raise ImmutablePredictionSnapshotError("快照输入输出证券必须一致")
        if any(
            left != right
            for left, right in (
                (prediction_input.data_version, prediction_output.data_version),
                (prediction_input.feature_version, prediction_output.feature_version),
                (prediction_input.model_version, prediction_output.model_version),
                (
                    prediction_input.prediction_label_rule_version,
                    prediction_output.label_rule_version,
                ),
                (prediction_input.freshness, prediction_output.freshness),
            )
        ):
            raise ImmutablePredictionSnapshotError("快照输入输出版本或新鲜度必须一致")
        if (trading_calendar is None) != (prediction_label_rule is None):
            raise ImmutablePredictionSnapshotError("快照日历与标签规则必须同时绑定")
        if trading_calendar is not None and (
            trading_calendar.version_id != prediction_input.trading_calendar_version
            or prediction_label_rule is None
            or prediction_label_rule.version_id != prediction_input.prediction_label_rule_version
        ):
            raise ImmutablePredictionSnapshotError("快照日历或标签规则版本必须与预测输入一致")
        snapshot = PredictionSnapshot(
            snapshot_id,
            prediction_input.model_copy(deep=True),
            prediction_output.model_copy(deep=True),
            prediction_input.predicted_at,
            (
                outcome_fact_value("TRADING_CALENDAR", trading_calendar)
                if trading_calendar is not None
                else None
            ),
            (
                outcome_fact_value("LABEL_RULE", prediction_label_rule)
                if prediction_label_rule is not None
                else None
            ),
        )
        self._snapshots[snapshot_id] = snapshot
        return PredictionSnapshot(
            snapshot.snapshot_id,
            snapshot.prediction_input.model_copy(deep=True),
            snapshot.prediction_output.model_copy(deep=True),
            snapshot.generated_at,
            snapshot.trading_calendar_fact_value,
            snapshot.label_rule_fact_value,
        )

    def append_actual_outcome(self, outcome: ActualOutcome) -> ActualOutcome:
        if outcome.prediction_snapshot_id not in self._snapshots or self._outcomes.get(
            outcome.prediction_snapshot_id
        ):
            raise ImmutablePredictionSnapshotError("到期结果只能追加且不可重复或覆盖")
        snapshot = self._snapshots[outcome.prediction_snapshot_id]
        if outcome.prediction_time != snapshot.prediction_input.predicted_at:
            raise ImmutablePredictionSnapshotError("到期结果预测时点必须由快照派生")
        if outcome.horizon_trading_days != snapshot.prediction_output.horizon_trading_days:
            raise ImmutablePredictionSnapshotError("到期结果周期必须由快照派生")
        if outcome.trading_calendar_version != snapshot.prediction_input.trading_calendar_version:
            raise ImmutablePredictionSnapshotError("到期结果日历版本必须与快照一致")
        if outcome.label_rule_version != snapshot.prediction_input.prediction_label_rule_version:
            raise ImmutablePredictionSnapshotError("到期结果规则版本必须与快照一致")
        if snapshot.trading_calendar_fact_value is None or snapshot.label_rule_fact_value is None:
            raise ImmutablePredictionSnapshotError("预测快照未绑定日历与标签规则内容")
        if outcome.status is not ActualOutcomeStatus.VALIDATED or not outcome.fact_references:
            raise ImmutablePredictionSnapshotError("只有已验证且绑定事实引用的到期结果可以持久化")
        if any(
            reference.security_id != snapshot.prediction_input.security_id
            or reference.prediction_snapshot_id != outcome.prediction_snapshot_id
            or reference.prediction_time != outcome.prediction_time
            or reference.version_id == "UNSPECIFIED"
            for reference in outcome.fact_references
        ):
            raise ImmutablePredictionSnapshotError("到期事实必须与快照证券、时点和版本绑定")
        price_references = tuple(
            reference
            for reference in outcome.fact_references
            if reference.fact_type in {"REFERENCE_PRICE", "EXPIRY_PRICE"}
        )
        if len(price_references) != 2 or any(
            reference.version_id != snapshot.prediction_input.data_version
            for reference in price_references
        ):
            raise ImmutablePredictionSnapshotError("到期价格事实数据版本必须与预测快照一致")
        self._verify_outcome_facts(snapshot, outcome)
        stored = ActualOutcome(**outcome.__dict__)
        self._outcomes.setdefault(outcome.prediction_snapshot_id, []).append(stored)
        return stored

    def actual_outcomes_for(self, snapshot_id: str) -> tuple[ActualOutcome, ...]:
        return tuple(self._outcomes.get(snapshot_id, ()))

    @staticmethod
    def _verify_outcome_facts(snapshot: PredictionSnapshot, outcome: ActualOutcome) -> None:
        """在持久化边界重验签名、交易日、规则和标签，拒绝绕过解析器的 DTO。"""

        expected_types = {
            "REFERENCE_PRICE",
            "EXPIRY_PRICE",
            "REFERENCE_TRADABILITY",
            "EXPIRY_TRADABILITY",
            "TRADING_CALENDAR",
            "LABEL_RULE",
            "COMPANY_ACTIONS",
        }
        try:
            rebuilt = tuple(
                OutcomeFactReference(**reference.model_dump())
                for reference in outcome.fact_references
            )
            facts = {reference.fact_type: reference for reference in rebuilt}
            if len(facts) != len(rebuilt) or set(facts) != expected_types:
                raise ValueError("到期事实类型不完整或重复")
            if not all(_is_trusted_outcome_fact(reference) for reference in rebuilt):
                raise ValueError("到期事实未由受信签发方签名")
            if any(reference.available_at > outcome.validated_at for reference in rebuilt):
                raise ValueError("到期事实晚于验证边界")
            security_id = snapshot.prediction_input.security_id
            prediction_time = snapshot.prediction_input.predicted_at
            reference_price_fact = facts["REFERENCE_PRICE"]
            if (
                reference_price_fact.market_time > prediction_time
                or reference_price_fact.collected_at > prediction_time
                or reference_price_fact.available_at > prediction_time
            ):
                raise ValueError("参考价格事实晚于预测时点")
            if _market_date(outcome.validated_at, security_id) <= outcome.expiry_trading_day:
                raise ValueError("验证时点必须晚于到期交易日")
            if (
                facts["REFERENCE_TRADABILITY"].fact_value != "TRADABLE"
                or facts["EXPIRY_TRADABILITY"].fact_value != "TRADABLE"
            ):
                raise ValueError("两端必须有可交易状态事实")
            reference_price = Decimal(facts["REFERENCE_PRICE"].fact_value)
            expiry_price = Decimal(facts["EXPIRY_PRICE"].fact_value)
            if (
                not reference_price.is_finite()
                or not expiry_price.is_finite()
                or facts["REFERENCE_PRICE"].fact_value != _canonical_decimal(reference_price)
                or facts["EXPIRY_PRICE"].fact_value != _canonical_decimal(expiry_price)
                or reference_price != outcome.reference_total_return_adjusted_price
                or expiry_price != outcome.expiry_total_return_adjusted_price
                or reference_price <= 0
                or expiry_price <= 0
            ):
                raise ValueError("价格事实与到期结果不一致")
            if (
                _market_date(facts["REFERENCE_PRICE"].market_time, security_id)
                != outcome.reference_trading_day
            ):
                raise ValueError("参考价格事实市场日期不匹配")
            if (
                _market_date(facts["EXPIRY_PRICE"].market_time, security_id)
                != outcome.expiry_trading_day
            ):
                raise ValueError("到期价格事实市场日期不匹配")
            market = getattr(security_id.market, "value", security_id.market)
            if (
                facts["TRADING_CALENDAR"].version_id != outcome.trading_calendar_version
                or facts["LABEL_RULE"].version_id != outcome.label_rule_version
            ):
                raise ValueError("日历或规则事实与快照不匹配")
            calendar = _rebuild_calendar_outcome_fact(
                facts["TRADING_CALENDAR"].fact_value,
                expected_market=market,
                expected_version=outcome.trading_calendar_version,
            )
            rule = _rebuild_label_rule_outcome_fact(
                facts["LABEL_RULE"].fact_value, expected_version=outcome.label_rule_version
            )
            if (
                facts["TRADING_CALENDAR"].fact_value != snapshot.trading_calendar_fact_value
                or facts["LABEL_RULE"].fact_value != snapshot.label_rule_fact_value
            ):
                raise ValueError("日历或规则内容与预测快照不一致")
            actions = _rebuild_company_actions_outcome_fact(
                facts["COMPANY_ACTIONS"].fact_value,
                security_id=security_id,
                expected_market=market,
            )
            if any(
                action.effective_at > outcome.validated_at
                or (action.available_at is not None and action.available_at > outcome.validated_at)
                for action in actions
            ):
                raise ValueError("公司行动事实在验证边界后才生效或可得")
            trading_days = sorted(calendar.trading_days)
            if (
                outcome.reference_trading_day not in trading_days
                or outcome.expiry_trading_day not in trading_days
                or trading_days.index(outcome.expiry_trading_day)
                != trading_days.index(outcome.reference_trading_day) + outcome.horizon_trading_days
            ):
                raise ValueError("交易日历不支持到期边界")
            threshold = rule.thresholds[outcome.horizon_trading_days]
            change = expiry_price / reference_price - Decimal("1")
            expected_label = (
                PredictionLabel.UP
                if change >= threshold
                else PredictionLabel.DOWN
                if change <= -threshold
                else PredictionLabel.FLAT
            )
            if outcome.label is not expected_label:
                raise ValueError("到期标签不是由已签名事实推导")
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ImmutablePredictionSnapshotError("到期事实或标签未通过持久化复验") from exc


def generate_simple_baseline_prediction(
    prediction_input: PredictionInput,
    *,
    horizon_trading_days: int,
    primary_evidence: tuple[str, ...],
    risk_factors: tuple[str, ...],
    quantitative_fact_references: tuple[QuantitativeFactReference, ...],
) -> PredictionOutput:
    """基于预测时点已可得的本地事实生成固定简单基准概率，不训练、发布或交易。"""
    if any(reference.reference_type != "LOCAL" for reference in quantitative_fact_references):
        raise CurrentPredictionUnavailableError("简单基准只接受预测时点可用的本地事实")
    if any(
        reference.prediction_time > prediction_input.predicted_at
        or reference.called_at > prediction_input.predicted_at
        or reference.data_as_of > prediction_input.predicted_at
        for reference in quantitative_fact_references
    ):
        raise CurrentPredictionUnavailableError("简单基准不得使用未来事实")
    if any(
        reference.security_id != prediction_input.security_id
        or reference.data_version != prediction_input.data_version
        or reference.feature_version != prediction_input.feature_version
        or reference.model_version != prediction_input.model_version
        or reference.label_rule_version != prediction_input.prediction_label_rule_version
        for reference in quantitative_fact_references
    ):
        raise CurrentPredictionUnavailableError("简单基准事实必须与输入证券和版本强绑定")
    return PredictionOutput(
        security_id=prediction_input.security_id,
        predicted_at=prediction_input.predicted_at,
        data_version=prediction_input.data_version,
        feature_version=prediction_input.feature_version,
        horizon_trading_days=horizon_trading_days,
        up_probability=Decimal("34"),
        flat_probability=Decimal("33"),
        down_probability=Decimal("33"),
        confidence=Decimal("0.5"),
        primary_evidence=primary_evidence,
        risk_factors=risk_factors,
        freshness=prediction_input.freshness,
        model_version=prediction_input.model_version,
        label_rule_version=prediction_input.prediction_label_rule_version or "",
        disclaimer=FIXED_RESEARCH_DISCLAIMER,
        quantitative_fact_references=quantitative_fact_references,
    )
