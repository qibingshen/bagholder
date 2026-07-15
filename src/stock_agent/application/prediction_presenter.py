"""组装预测展示结果，并复核数字溯源和固定风险提示。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_agent.domain.prediction import (
    FIXED_RESEARCH_DISCLAIMER,
    PredictionSnapshot,
    QuantitativeFactReference,
)


class PredictionPresentationError(ValueError):
    """表示预测展示结果缺少溯源、风险提示或包含越界文案。"""


@dataclass(frozen=True, slots=True)
class PredictionPresentation:
    """面向桌面端、报告和 AI 解释的只读预测展示模型。"""

    snapshot_id: str
    security_key: str
    horizon_trading_days: int
    probabilities: dict[str, Decimal]
    confidence: Decimal
    primary_evidence: tuple[str, ...]
    risk_factors: tuple[str, ...]
    freshness_state: str
    display_state: str
    version_summary: dict[str, str]
    disclaimer: str
    fact_references_by_field: dict[str, QuantitativeFactReference]


class PredictionPresenter:
    """把已验证预测快照转换为展示模型，不重新计算任何量化数字。"""

    def present(self, snapshot: PredictionSnapshot) -> PredictionPresentation:
        """返回含概率、依据、风险、版本和事实引用的展示结果。"""

        output = snapshot.prediction_output
        _ensure_safe_text((*output.primary_evidence, *output.risk_factors, output.disclaimer))
        if output.disclaimer != FIXED_RESEARCH_DISCLAIMER:
            raise PredictionPresentationError("预测展示必须包含固定投资建议风险提示")
        references = _references_by_field(output.quantitative_fact_references)
        values = {
            "up_probability": Decimal(str(output.up_probability)),
            "flat_probability": Decimal(str(output.flat_probability)),
            "down_probability": Decimal(str(output.down_probability)),
            "confidence": Decimal(str(output.confidence)),
        }
        for field_name, value in values.items():
            evidence = references[field_name].field_evidence[0]
            if evidence.numeric_value != value:
                raise PredictionPresentationError(f"{field_name} 数字与事实引用不一致")
        return PredictionPresentation(
            snapshot_id=snapshot.snapshot_id,
            security_key=_security_key(output.security_id),
            horizon_trading_days=output.horizon_trading_days,
            probabilities={
                "up": values["up_probability"],
                "flat": values["flat_probability"],
                "down": values["down_probability"],
            },
            confidence=values["confidence"],
            primary_evidence=output.primary_evidence,
            risk_factors=output.risk_factors,
            freshness_state=output.freshness,
            display_state=snapshot.display_state_for_current_data(output.freshness).value,
            version_summary={
                "data_version": output.data_version,
                "feature_version": output.feature_version or "",
                "model_version": output.model_version,
                "label_rule_version": output.label_rule_version or "",
            },
            disclaimer=output.disclaimer,
            fact_references_by_field=references,
        )


def _references_by_field(
    references: tuple[QuantitativeFactReference, ...],
) -> dict[str, QuantitativeFactReference]:
    """按展示数字字段建立唯一事实引用索引。"""

    required = {"up_probability", "flat_probability", "down_probability", "confidence"}
    result: dict[str, QuantitativeFactReference] = {}
    for reference in references:
        for field_name in reference.covered_fields:
            if field_name in result:
                raise PredictionPresentationError(f"{field_name} 事实引用重复")
            result[field_name] = reference
    missing = required - set(result)
    if missing:
        missing_text = "、".join(sorted(missing))
        raise PredictionPresentationError(f"缺少数字事实引用：{missing_text}")
    return result


def _ensure_safe_text(items: tuple[str, ...]) -> None:
    """展示文案不得混入收益承诺、买卖指令或替代投资建议。"""

    blocked_terms = ("保证", "收益", "买入", "卖出", "立即买", "交易指令")
    text = " ".join(items)
    if any(term in text for term in blocked_terms):
        raise PredictionPresentationError("预测展示不得包含收益承诺、买卖指令或投资建议")


def _security_key(security_id: object) -> str:
    market = getattr(getattr(security_id, "market", ""), "value", "")
    exchange = getattr(security_id, "exchange", "")
    display_code = getattr(security_id, "display_code", "")
    return f"{market}:{exchange}:{display_code}"
