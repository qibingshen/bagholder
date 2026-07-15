"""验证预测标签和概率展示的性质约束，不生成预测或交易。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from math import inf, nan

import pytest
from hypothesis import given
from hypothesis import strategies as st
from stock_agent.domain.prediction import (
    PredictionLabel,
    PredictionLabelRuleError,
    classify_prediction_label,
    validate_prediction_probabilities,
)

from stock_agent.domain.market_rules import TradingCalendar

允许周期 = (1, 5, 20)
阈值 = {
    1: Decimal("0.01"),
    5: Decimal("0.03"),
    20: Decimal("0.06"),
}


def 市场日历(交易日: set[date], 版本: str = "calendar-us-v1") -> TradingCalendar:
    """构造带版本的本地市场日历事实，避免测试依赖自然日或外部数据。"""

    return TradingCalendar(market="US", version_id=版本, trading_days=frozenset(交易日))


def 完整市场日历(周期: int, 版本: str = "calendar-us-v1") -> TradingCalendar:
    """为指定交易日周期构造最小完整日历事实，不以自然日间隔替代计数。"""

    参考交易日 = date(2026, 7, 14)
    return 市场日历(
        {参考交易日 + timedelta(days=偏移) for 偏移 in range(周期 + 1)},
        版本,
    )


def 标签(
    *,
    周期: int,
    收益率: Decimal,
    日历: TradingCalendar,
    预测时点: datetime = datetime(2026, 7, 14, tzinfo=UTC),
    到期价格可得时点: datetime | None = None,
    日历可得时点: datetime | None = None,
    特征可得时点: datetime | None = None,
) -> PredictionLabel:
    """以固定参考价将收益率转换为总回报复权价格，集中表达标签契约输入。"""

    参考交易日 = date(2026, 7, 14)
    到期交易日 = 参考交易日 + timedelta(days=周期)
    return classify_prediction_label(
        horizon_trading_days=周期,
        reference_trading_day=参考交易日,
        expiry_trading_day=到期交易日,
        trading_calendar=日历,
        trading_calendar_version=日历.version_id,
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=Decimal("100") * (Decimal("1") + 收益率),
        prediction_time=预测时点,
        expiry_price_available_at=到期价格可得时点 or 预测时点,
        calendar_available_at=日历可得时点 or 预测时点,
        feature_available_at=特征可得时点 or 预测时点,
    )


@pytest.mark.parametrize("周期", 允许周期)
@given(st.decimals(min_value="-0.50", max_value="0.50", places=4))
def test_总回报复权收益率按阈值分类为涨跌(周期: int, 收益率: Decimal) -> None:
    """任意有限总回报收益率都必须按周期阈值，达到正阈值或负阈值即归入涨跌。"""

    日历 = 完整市场日历(周期)
    预期 = (
        PredictionLabel.UP
        if 收益率 >= 阈值[周期]
        else PredictionLabel.DOWN
        if 收益率 <= -阈值[周期]
        else PredictionLabel.FLAT
    )

    assert 标签(周期=周期, 收益率=收益率, 日历=日历) is 预期


@pytest.mark.parametrize("周期", 允许周期)
def test_总回报收益率恰好处于正负阈值时归为涨跌(周期: int) -> None:
    """正负边界不因浮点或比较符号歧义被误判成震荡。"""

    日历 = 完整市场日历(周期)

    assert 标签(周期=周期, 收益率=阈值[周期], 日历=日历) is PredictionLabel.UP
    assert 标签(周期=周期, 收益率=-阈值[周期], 日历=日历) is PredictionLabel.DOWN


@given(st.integers(min_value=-100, max_value=100).filter(lambda 周期: 周期 not in 允许周期))
def test_仅接受规定的市场交易日周期(周期: int) -> None:
    """任意非 1、5、20 的周期均不得被当作自然日或其他交易日周期接受。"""

    日历 = 完整市场日历(1)

    with pytest.raises(PredictionLabelRuleError, match="交易日"):
        标签(周期=周期, 收益率=Decimal("0"), 日历=日历)


@pytest.mark.parametrize("周期", 允许周期)
def test_交易日数量必须以传入且版本匹配的市场日历为准(周期: int) -> None:
    """跨周末的自然日间隔不能替代传入日历中可追溯的交易日计数。"""

    参考交易日 = date(2026, 7, 14)
    到期交易日 = 参考交易日 + timedelta(days=周期)
    缺少中间交易日的日历 = 市场日历({参考交易日, 到期交易日})

    with pytest.raises(PredictionLabelRuleError, match="日历|交易日"):
        标签(周期=周期, 收益率=Decimal("0"), 日历=缺少中间交易日的日历)

    完整交易日 = {参考交易日 + timedelta(days=天数) for 天数 in range(周期 + 1)}
    完整日历 = 市场日历(完整交易日, 版本="calendar-us-v2")
    with pytest.raises(PredictionLabelRuleError, match="日历版本"):
        classify_prediction_label(
            horizon_trading_days=周期,
            reference_trading_day=参考交易日,
            expiry_trading_day=到期交易日,
            trading_calendar=完整日历,
            trading_calendar_version="calendar-us-v1",
            reference_total_return_adjusted_price=Decimal("100"),
            expiry_total_return_adjusted_price=Decimal("100"),
            prediction_time=datetime(2026, 7, 14, tzinfo=UTC),
            expiry_price_available_at=datetime(2026, 7, 14, tzinfo=UTC),
            calendar_available_at=datetime(2026, 7, 14, tzinfo=UTC),
            feature_available_at=datetime(2026, 7, 14, tzinfo=UTC),
        )


@given(st.integers(min_value=1, max_value=86_400))
def test_预测时点拒绝未来到期价格日历或特征(未来秒数: int) -> None:
    """任何晚于预测时点才可得的到期价格、日历版本或特征都不得进入标签计算。"""

    预测时点 = datetime(2026, 7, 14, tzinfo=UTC)
    日历 = 完整市场日历(1)
    未来时点 = 预测时点 + timedelta(seconds=未来秒数)

    for 字段 in ("到期价格可得时点", "日历可得时点", "特征可得时点"):
        参数: dict[str, datetime] = {字段: 未来时点}
        with pytest.raises(PredictionLabelRuleError, match="预测时点|未来"):
            标签(周期=1, 收益率=Decimal("0"), 日历=日历, 预测时点=预测时点, **参数)


def test_缺失有效到期价格时拒绝而非猜测标签() -> None:
    """到期复权价格缺失时必须停止标签计算，不能以参考价或默认值伪造结果。"""

    with pytest.raises(PredictionLabelRuleError, match="到期价格"):
        classify_prediction_label(
            horizon_trading_days=1,
            reference_trading_day=date(2026, 7, 14),
            expiry_trading_day=date(2026, 7, 15),
            trading_calendar=完整市场日历(1),
            trading_calendar_version="calendar-us-v1",
            reference_total_return_adjusted_price=Decimal("100"),
            expiry_total_return_adjusted_price=None,
            prediction_time=datetime(2026, 7, 14, tzinfo=UTC),
            expiry_price_available_at=datetime(2026, 7, 14, tzinfo=UTC),
            calendar_available_at=datetime(2026, 7, 14, tzinfo=UTC),
            feature_available_at=datetime(2026, 7, 14, tzinfo=UTC),
        )


@given(
    st.decimals(min_value="0", max_value="100", places=3),
    st.decimals(min_value="0", max_value="100", places=3),
    st.decimals(min_value="0", max_value="100", places=3),
)
def test_概率分布只接受非负且总和位于百分之百正负零点一内(
    上涨概率: Decimal, 震荡概率: Decimal, 下跌概率: Decimal
) -> None:
    """任意有限三分类概率只在每项非负且总和落在允许容差内时通过验证。"""

    概率 = (上涨概率, 震荡概率, 下跌概率)
    总和 = sum(概率)
    if Decimal("99.9") <= 总和 <= Decimal("100.1"):
        validate_prediction_probabilities(*概率)
    else:
        with pytest.raises(PredictionLabelRuleError, match="概率"):
            validate_prediction_probabilities(*概率)


@pytest.mark.parametrize(
    "概率",
    [
        (-Decimal("0.001"), Decimal("50"), Decimal("50.001")),
        (Decimal("50"), -Decimal("0.001"), Decimal("50.001")),
        (Decimal("50"), Decimal("50.001"), -Decimal("0.001")),
        (nan, 50.0, 50.0),
        (inf, 50.0, 50.0),
        (-inf, 50.0, 50.0),
    ],
)
def test_概率拒绝负数非数和无穷值(
    概率: tuple[Decimal | float, Decimal | float, Decimal | float],
) -> None:
    """概率校验不能让负值、NaN 或正负无穷通过总和容差的边界。"""

    with pytest.raises(PredictionLabelRuleError, match="概率|有限"):
        validate_prediction_probabilities(*概率)
