"""验证预测标签、到期回填与概率展示的性质约束，不生成预测或交易。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from math import inf, nan

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from stock_agent.domain.market_rules import CompanyAction, TradingCalendar
from stock_agent.domain.prediction import (
    ActualOutcomeStatus,
    CurrentPredictionUnavailableError,
    OutcomeFactReference,
    PredictionInput,
    PredictionLabel,
    PredictionLabelRule,
    PredictionLabelRuleError,
    resolve_actual_outcome,
    validate_prediction_probabilities,
)

允许周期 = (1, 5, 20)
阈值 = {
    1: Decimal("0.01"),
    5: Decimal("0.03"),
    20: Decimal("0.06"),
}
规则_v1 = PredictionLabelRule(
    version_id="prediction-label-v1",
    thresholds=阈值,
)
预测时点 = datetime(2026, 7, 2, 9, 30, tzinfo=UTC)
参考交易日 = date(2026, 7, 2)

# 7 月 3 日为节假日，7 月 4 日和 5 日为周末，7 月 15 日为临时停牌日；均不能计作交易日。
有效交易日 = (
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 16),
    date(2026, 7, 17),
    date(2026, 7, 20),
    date(2026, 7, 21),
    date(2026, 7, 22),
    date(2026, 7, 23),
    date(2026, 7, 24),
    date(2026, 7, 27),
    date(2026, 7, 28),
    date(2026, 7, 29),
    date(2026, 7, 30),
    date(2026, 7, 31),
    date(2026, 8, 3),
    date(2026, 8, 4),
    *(
        date(2026, 8, 5) + timedelta(days=offset)
        for offset in range(180)
        if (date(2026, 8, 5) + timedelta(days=offset)).weekday() < 5
    ),
)


def 市场日历(
    交易日: tuple[date, ...] = 有效交易日, 版本: str = "calendar-us-v1"
) -> TradingCalendar:
    """构造带版本的市场日历事实，交易日只由显式市场事实决定。"""

    return TradingCalendar(market="US", version_id=版本, trading_days=frozenset(交易日))


def 到期交易日(周期: int, 日历: TradingCalendar) -> date:
    """按市场日历中的有效交易日序号取到期日，禁止以自然日 timedelta 推导。"""

    交易日 = tuple(sorted(日历.trading_days))
    return 交易日[交易日.index(参考交易日) + 周期]


def 预测输入负载(**覆盖: object) -> dict[str, object]:
    """返回预测生成阶段可见的事实；该阶段不应包含到期结果。"""

    负载: dict[str, object] = {
        "security_id": "US:NASDAQ:AAPL",
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
        "is_current_data_available": True,
    }
    负载.update(覆盖)
    return 负载


def 到期结果(
    *,
    周期: int,
    收益率: Decimal | None,
    日历: TradingCalendar,
    到期价格可得时点: datetime | None,
    标签规则: PredictionLabelRule = 规则_v1,
    传入到期日: date | None = None,
    传入日历版本: str | None = None,
    解析日历: TradingCalendar | None = None,
):
    """仅在到期验证阶段建立独立实际结果；此处允许价格晚于预测时点可得。"""

    到期日 = 传入到期日 or 到期交易日(周期, 日历)
    日历事实 = 解析日历 or 日历
    验证时点 = max(
        (到期价格可得时点 or 预测时点) + timedelta(seconds=1),
        datetime.combine(到期日, datetime.min.time(), tzinfo=UTC) + timedelta(days=1),
    )
    到期事实 = tuple(
        OutcomeFactReference(
            fact_type=事实类型,
            reference_type="LOCAL",
            source_id="local-verified-history",
            tool_name="local_fact_store",
            tool_version="v1",
            market_time=验证时点,
            collected_at=验证时点,
            available_at=验证时点,
            version_id=版本,
            result_id=f"{事实类型}:{版本}",
            result_anchor=f"local://outcomes/{事实类型}:{版本}",
            fact_value=f"{事实类型}:{版本}",
            value_hash=sha256(f"{事实类型}:{事实类型}:{版本}".encode()).hexdigest(),
        )
        for 事实类型, 版本 in (
            ("REFERENCE_PRICE", "daily-us-v1"),
            ("EXPIRY_PRICE", "daily-us-v1"),
            ("TRADING_CALENDAR", 日历事实.version_id),
            ("LABEL_RULE", 标签规则.version_id),
        )
    )
    return resolve_actual_outcome(
        prediction_snapshot_id="prediction:NASDAQ:AAPL:2026-07-02T09:30:00Z",
        prediction_time=预测时点,
        horizon_trading_days=周期,
        reference_trading_day=参考交易日,
        expiry_trading_day=到期日,
        trading_calendar=日历事实,
        trading_calendar_version=传入日历版本 or 日历事实.version_id,
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=(
            None if 收益率 is None else Decimal("100") * (Decimal("1") + 收益率)
        ),
        expiry_price_available_at=到期价格可得时点,
        validated_at=验证时点,
        prediction_label_rule=标签规则,
        outcome_fact_references=到期事实,
    )


@pytest.mark.parametrize("周期", 允许周期)
@given(st.decimals(min_value="-0.50", max_value="0.50", places=4))
def test_到期实际结果按快照规则版本和包含边界分类(周期: int, 收益率: Decimal) -> None:
    """到期结果以快照规则版本分类：达到正阈值上涨，达到负阈值下跌，其余震荡。"""

    日历 = 市场日历()
    预期 = (
        PredictionLabel.UP
        if 收益率 >= 阈值[周期]
        else PredictionLabel.DOWN
        if 收益率 <= -阈值[周期]
        else PredictionLabel.FLAT
    )

    结果 = 到期结果(
        周期=周期,
        收益率=收益率,
        日历=日历,
        到期价格可得时点=预测时点 + timedelta(days=31),
    )

    assert 结果.status is ActualOutcomeStatus.VALIDATED
    assert 结果.label is 预期
    assert 结果.label_rule_version == 规则_v1.version_id


@pytest.mark.parametrize("周期", 允许周期)
def test_到期实际结果在正负阈值恰好归为涨跌(周期: int) -> None:
    """1、5、20 日的精确正负阈值不因比较符号歧义被误判为震荡。"""

    日历 = 市场日历()
    可得时点 = 预测时点 + timedelta(days=31)

    assert (
        到期结果(周期=周期, 收益率=阈值[周期], 日历=日历, 到期价格可得时点=可得时点).label
        is PredictionLabel.UP
    )
    assert (
        到期结果(周期=周期, 收益率=-阈值[周期], 日历=日历, 到期价格可得时点=可得时点).label
        is PredictionLabel.DOWN
    )


@pytest.mark.parametrize(
    "周期, 预期到期日", [(1, date(2026, 7, 6)), (5, date(2026, 7, 10)), (20, date(2026, 8, 3))]
)
def test_周期按非连续市场交易日而非自然日计数(周期: int, 预期到期日: date) -> None:
    """周末、节假日与临停日不计入 1、5、20 个所属市场交易日。"""

    日历 = 市场日历()

    assert 到期交易日(周期, 日历) == 预期到期日
    assert 预期到期日 != 参考交易日 + timedelta(days=周期)


@pytest.mark.parametrize("周期", 允许周期)
def test_实际结果解析器拒绝自然日到期日和错日历版本(周期: int) -> None:
    """公开到期解析器必须自行校验市场交易日序号与日历版本，不能信任调用方。"""

    日历 = 市场日历()
    可得时点 = 预测时点 + timedelta(days=31)

    自然日到期日 = 参考交易日 + timedelta(days=周期)
    if not 日历.is_trading_day(自然日到期日):
        自然日到期结果 = 到期结果(
            周期=周期,
            收益率=Decimal("0"),
            日历=日历,
            到期价格可得时点=可得时点,
            传入到期日=自然日到期日,
        )
        assert 自然日到期结果.status is ActualOutcomeStatus.PENDING_VALIDATION
        assert 自然日到期结果.label is None
    else:
        with pytest.raises(PredictionLabelRuleError, match="交易日|到期日|日历"):
            到期结果(
                周期=周期,
                收益率=Decimal("0"),
                日历=日历,
                到期价格可得时点=可得时点,
                传入到期日=自然日到期日,
            )

    with pytest.raises(PredictionLabelRuleError, match="日历版本|日历"):
        到期结果(
            周期=周期,
            收益率=Decimal("0"),
            日历=日历,
            到期价格可得时点=可得时点,
            传入日历版本="calendar-us-v0",
        )

    错日历 = 市场日历(
        tuple(交易日 for 交易日 in 有效交易日 if 交易日 != 到期交易日(周期, 日历)),
        版本="calendar-us-v2",
    )
    非交易日到期结果 = 到期结果(
        周期=周期,
        收益率=Decimal("0"),
        日历=日历,
        解析日历=错日历,
        到期价格可得时点=可得时点,
    )
    assert 非交易日到期结果.status is ActualOutcomeStatus.PENDING_VALIDATION
    assert 非交易日到期结果.label is None


@given(st.integers(min_value=-100, max_value=100).filter(lambda 周期: 周期 not in 允许周期))
def test_到期结果拒绝非规定交易日周期(周期: int) -> None:
    """任意非 1、5、20 的周期不得被自然日或其他交易日周期替代。"""

    with pytest.raises(PredictionLabelRuleError, match="交易日"):
        到期结果(
            周期=周期,
            收益率=Decimal("0"),
            日历=市场日历(),
            到期价格可得时点=预测时点 + timedelta(days=31),
        )


def test_预测输入拒绝到期价格且到期回填允许价格晚于预测时点() -> None:
    """预测生成不能读取未来到期价；到期后独立回填可以使用当时才可得的价格。"""

    with pytest.raises(ValidationError, match="到期价格|预测输入|额外"):
        PredictionInput(
            **预测输入负载(
                expiry_total_return_adjusted_price=Decimal("101"),
                expiry_price_available_at=预测时点 + timedelta(days=31),
            )
        )

    结果 = 到期结果(
        周期=1,
        收益率=Decimal("0.01"),
        日历=市场日历(),
        到期价格可得时点=预测时点 + timedelta(days=31),
    )
    assert 结果.status is ActualOutcomeStatus.VALIDATED
    assert 结果.label is PredictionLabel.UP


@pytest.mark.parametrize(
    "字段",
    ["calendar_available_at", "feature_available_at", "feature_cutoff_at"],
)
def test_预测输入拒绝预测时点后才可得的日历版本或特征事实(字段: str) -> None:
    """预测输入必须携带日历版本及可得时点、特征和截止时点，且均不得晚于预测时点。"""

    with pytest.raises(CurrentPredictionUnavailableError, match="日历|特征|截止|预测时点|未来"):
        PredictionInput(**预测输入负载(**{字段: 预测时点 + timedelta(seconds=1)}))


def test_缺失有效到期价格保持待验证且不可强行分类() -> None:
    """到期价格缺失必须形成 PENDING_VALIDATION，不能抛错后伪造方向标签。"""

    结果 = 到期结果(周期=5, 收益率=None, 日历=市场日历(), 到期价格可得时点=None)

    assert 结果.status is ActualOutcomeStatus.PENDING_VALIDATION
    assert 结果.label is None
    assert 结果.expiry_total_return_adjusted_price is None


def test_预测输入拒绝预测时点后生效的公司行动() -> None:
    """未来公司行动不能进入预测输入或复权特征，避免以事后事实污染预测。"""

    未来行动 = CompanyAction(
        action_id="split-aapl-20260703",
        action_type="split",
        effective_at=预测时点 + timedelta(days=1),
        version_id="action-us-v2",
        source_id="authorized-source",
    )

    with pytest.raises(CurrentPredictionUnavailableError, match="公司行动|预测时点|未来"):
        PredictionInput(**预测输入负载(company_actions=(未来行动,)))


def test_到期结果按快照规则阈值分类且不得被新版规则回写() -> None:
    """同一收益率在 v1/v2 阈值不同；历史实际结果必须使用预测快照捕获的 v1。"""

    规则_v2 = PredictionLabelRule(
        version_id="prediction-label-v2",
        thresholds={1: Decimal("0.02"), 5: Decimal("0.04"), 20: Decimal("0.07")},
    )
    收益率 = Decimal("0.015")

    原结果 = 到期结果(
        周期=1,
        收益率=收益率,
        日历=市场日历(),
        到期价格可得时点=预测时点 + timedelta(days=31),
        标签规则=规则_v1,
    )
    新规则结果 = 到期结果(
        周期=1,
        收益率=收益率,
        日历=市场日历(),
        到期价格可得时点=预测时点 + timedelta(days=31),
        标签规则=规则_v2,
    )

    assert 原结果.label_rule_version == 规则_v1.version_id
    assert 原结果.label is PredictionLabel.UP
    assert 新规则结果.label_rule_version == 规则_v2.version_id
    assert 新规则结果.label is PredictionLabel.FLAT
    with pytest.raises(PredictionLabelRuleError, match="规则版本|回写|不可变"):
        原结果.with_label_rule_version("prediction-label-v2")


@given(
    st.decimals(min_value="-1", max_value="101", places=3),
    st.decimals(min_value="-1", max_value="101", places=3),
    st.decimals(min_value="-1", max_value="101", places=3),
)
def test_概率仅接受每项零至一百且总和在容差内(上涨: Decimal, 震荡: Decimal, 下跌: Decimal) -> None:
    """三项均须在 0 至 100，且总和只能落在 100% 正负 0.1 个百分点内。"""

    概率 = (上涨, 震荡, 下跌)
    总和 = sum(概率)
    if all(Decimal("0") <= 值 <= Decimal("100") for 值 in 概率) and Decimal(
        "99.9"
    ) <= 总和 <= Decimal("100.1"):
        validate_prediction_probabilities(*概率)
    else:
        with pytest.raises(PredictionLabelRuleError, match="概率"):
            validate_prediction_probabilities(*概率)


@pytest.mark.parametrize(
    "概率",
    [
        (Decimal("100.05"), Decimal("0"), Decimal("0")),
        (Decimal("100.01"), Decimal("-0.01"), Decimal("0")),
        (nan, 50.0, 50.0),
        (inf, 50.0, 50.0),
        (-inf, 50.0, 50.0),
    ],
)
def test_概率拒绝单项越界与非有限值(
    概率: tuple[Decimal | float, Decimal | float, Decimal | float],
) -> None:
    """总和即使落入容差，单项 100.05、负数、NaN 或无穷也必须拒绝。"""

    with pytest.raises(PredictionLabelRuleError, match="概率|有限"):
        validate_prediction_probabilities(*概率)
