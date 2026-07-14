"""验证预测输入、输出和不可变快照的量化安全契约。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stock_agent.domain.market import InstrumentIdentity, Market
from stock_agent.domain.prediction import (
    FIXED_RESEARCH_DISCLAIMER,
    CurrentPredictionUnavailableError,
    ImmutablePredictionSnapshotError,
    PredictionDisplayState,
    PredictionInput,
    PredictionOutput,
    PredictionSnapshotStore,
    QuantitativeFactReference,
)


def 完整证券身份() -> InstrumentIdentity:
    """构造仅供预测契约使用的美国证券身份。"""

    return InstrumentIdentity(
        market=Market.US,
        exchange="NASDAQ",
        display_code="AAPL",
        currency="USD",
    )


def 完整预测输入() -> dict[str, object]:
    """返回可审计预测输入所需的全部事实字段。"""

    market_time = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
    return {
        "security_id": 完整证券身份(),
        "predicted_at": market_time,
        "market_time": market_time,
        "collected_at": market_time,
        "data_version": "daily-us-v1",
        "feature_version": "features-v1",
        "model_version": "baseline-v1",
        "is_current_data_available": True,
    }


def 量化事实引用(覆盖字段: str) -> QuantitativeFactReference:
    """构造覆盖单个量化字段且与预测元数据一致的本地事实引用。"""

    return QuantitativeFactReference(
        reference_type="LOCAL",
        result_id="daily-us-v1:NASDAQ:AAPL:2026-07-14",
        source_id="local-daily-bars",
        security_id=完整证券身份(),
        prediction_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        data_version="daily-us-v1",
        model_version="baseline-v1",
        covered_fields=(覆盖字段,),
    )


def 完整预测输出() -> dict[str, object]:
    """返回一个仅用于验证契约结构的合规预测负载。"""

    return {
        "security_id": 完整证券身份(),
        "predicted_at": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        "data_version": "daily-us-v1",
        "horizon_trading_days": 5,
        "up_probability": 42.5,
        "flat_probability": 35.0,
        "down_probability": 22.5,
        "confidence": 0.61,
        "primary_evidence": ("五日均线高于二十日均线",),
        "risk_factors": ("财报披露前波动可能放大",),
        "freshness": "REALTIME",
        "model_version": "baseline-v1",
        "disclaimer": FIXED_RESEARCH_DISCLAIMER,
        "quantitative_fact_references": tuple(
            量化事实引用(字段)
            for 字段 in ("up_probability", "flat_probability", "down_probability", "confidence")
        ),
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("security_id", None),
        ("predicted_at", None),
        ("market_time", None),
        ("collected_at", None),
        ("data_version", ""),
        ("feature_version", ""),
        ("model_version", ""),
        ("is_current_data_available", None),
    ],
)
def test_预测输入拒绝缺少身份时点版本或可用性事实(field: str, value: object) -> None:
    """缺少任一可审计输入事实时，当前预测不得进入模型计算。"""

    payload = 完整预测输入()
    payload[field] = value

    with pytest.raises(ValidationError):
        PredictionInput(**payload)


def test_预测输入拒绝当前数据不可用() -> None:
    """过期、缺失或未验证的当前数据必须在预测输入边界被拒绝。"""

    payload = 完整预测输入()
    payload["is_current_data_available"] = False

    with pytest.raises(CurrentPredictionUnavailableError, match="不可用"):
        PredictionInput(**payload)


@pytest.mark.parametrize("horizon", [1, 5, 20])
def test_预测输出仅接受规定交易日周期并保留固定风险提示(horizon: int) -> None:
    """预测只能面向 1、5、20 个交易日，且必须原样携带固定研究提示。"""

    payload = 完整预测输出()
    payload["horizon_trading_days"] = horizon

    output = PredictionOutput(**payload)

    assert output.horizon_trading_days == horizon
    assert output.disclaimer == "研究参考，不构成投资建议"


def test_预测输出拒绝非规定交易日周期() -> None:
    """任意非 1、5、20 个交易日的周期均不得展示为预测结果。"""

    payload = 完整预测输出()
    payload["horizon_trading_days"] = 10

    with pytest.raises(ValidationError, match="交易日"):
        PredictionOutput(**payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("confidence", None),
        ("primary_evidence", ()),
        ("risk_factors", ()),
        ("freshness", ""),
        ("model_version", ""),
        ("disclaimer", None),
    ],
)
def test_预测输出拒绝缺少规定安全字段(field: str, value: object) -> None:
    """置信度、依据、风险、新鲜度、模型版本和固定提示均为不可省略字段。"""

    payload = 完整预测输出()
    payload[field] = value

    with pytest.raises(ValidationError):
        PredictionOutput(**payload)


def test_预测输出拒绝不是字面固定值的风险提示() -> None:
    """风险提示即使语义相近也必须与规定中文文案逐字一致。"""

    payload = 完整预测输出()
    payload["disclaimer"] = "仅供研究参考，不构成投资建议。"

    with pytest.raises(ValidationError, match="研究参考，不构成投资建议"):
        PredictionOutput(**payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("up_probability", -0.1),
        ("flat_probability", -0.1),
        ("down_probability", -0.1),
        ("up_probability", 42.7),
    ],
)
def test_预测输出拒绝负概率或总和超出允许容差(field: str, value: float) -> None:
    """上涨、震荡、下跌概率必须非负，且总和只能在 100% 正负 0.1 个百分点内。"""

    payload = 完整预测输出()
    payload[field] = value

    with pytest.raises(ValidationError, match="概率"):
        PredictionOutput(**payload)


@pytest.mark.parametrize("down_probability", [29.9, 30.0, 30.1])
def test_预测输出接受概率总和处于容差边界的结果(down_probability: float) -> None:
    """概率总和为 99.9、100.0、100.1 时仍处于允许展示的边界内。"""

    payload = 完整预测输出()
    payload.update(up_probability=40.0, flat_probability=30.0, down_probability=down_probability)

    output = PredictionOutput(**payload)

    assert output.up_probability + output.flat_probability + output.down_probability == pytest.approx(
        70.0 + down_probability, abs=1e-9
    )


@pytest.mark.parametrize("down_probability", [29.89, 30.11])
def test_预测输出拒绝概率总和刚越过容差边界的结果(down_probability: float) -> None:
    """概率总和为 99.89 或 100.11 时必须拒绝，并避免浮点误差放宽边界。"""

    payload = 完整预测输出()
    payload.update(up_probability=40.0, flat_probability=30.0, down_probability=down_probability)

    with pytest.raises(ValidationError, match="概率"):
        PredictionOutput(**payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("disclaimer", "预测收益可保证达到 10%"),
        ("primary_evidence", ("建议立即买入",)),
        ("risk_factors", ("保证不会亏损",)),
    ],
)
def test_预测输出拒绝收益承诺或买卖指令(field: str, value: object) -> None:
    """研究输出不得混入收益承诺、保证性表述或买卖指令。"""

    payload = 完整预测输出()
    payload[field] = value

    with pytest.raises(ValidationError, match="投资建议|收益承诺|买卖指令"):
        PredictionOutput(**payload)


def test_预测输出拒绝没有结构化事实引用的量化数字() -> None:
    """概率、置信度等数值没有 MCP 或本地事实引用时必须拒绝输出。"""

    payload = 完整预测输出()
    payload["quantitative_fact_references"] = ()

    with pytest.raises(ValidationError, match="事实引用"):
        PredictionOutput(**payload)


def test_预测输出拒绝未覆盖量化字段的无关引用() -> None:
    """引用存在但未声明覆盖概率或置信度时，不能为任何量化数字背书。"""

    payload = 完整预测输出()
    payload["quantitative_fact_references"] = (量化事实引用("unrelated_metric"),)

    with pytest.raises(ValidationError, match="覆盖.*字段|事实引用"):
        PredictionOutput(**payload)


def test_预测输出拒绝非MCP或LOCAL类型的量化事实引用() -> None:
    """量化数字只能引用 MCP 或本地事实，不能接受自定义或未知引用类型。"""

    payload = 完整预测输出()
    payload["quantitative_fact_references"] = tuple(
        量化事实引用(字段).model_copy(update={"reference_type": "REMOTE"})
        for 字段 in ("up_probability", "flat_probability", "down_probability", "confidence")
    )

    with pytest.raises(ValidationError, match="MCP|LOCAL"):
        PredictionOutput(**payload)


@pytest.mark.parametrize(
    ("reference_field", "reference_value"),
    [
        ("security_id", InstrumentIdentity(market=Market.US, exchange="NYSE", display_code="MSFT", currency="USD")),
        ("prediction_time", datetime(2026, 7, 14, 9, 31, tzinfo=UTC)),
        ("data_version", "daily-us-v2"),
        ("model_version", "baseline-v2"),
    ],
)
def test_预测输出拒绝与预测元数据不匹配的量化事实引用(
    reference_field: str, reference_value: object
) -> None:
    """引用的证券、预测时点、数据版本和模型版本必须逐项匹配预测输出。"""

    payload = 完整预测输出()
    payload["quantitative_fact_references"] = tuple(
        量化事实引用(字段).model_copy(update={reference_field: reference_value})
        for 字段 in ("up_probability", "flat_probability", "down_probability", "confidence")
    )

    with pytest.raises(ValidationError, match="证券|时点|数据版本|模型版本|事实引用"):
        PredictionOutput(**payload)


@pytest.mark.parametrize("missing_field", ["up_probability", "flat_probability", "down_probability", "confidence"])
def test_预测输出拒绝有数值却没有逐项覆盖引用(missing_field: str) -> None:
    """上涨、震荡、下跌概率和置信度必须各有至少一个结构化事实引用。"""

    payload = 完整预测输出()
    payload["quantitative_fact_references"] = tuple(
        量化事实引用(字段)
        for 字段 in ("up_probability", "flat_probability", "down_probability", "confidence")
        if 字段 != missing_field
    )

    with pytest.raises(ValidationError, match="覆盖.*字段|事实引用"):
        PredictionOutput(**payload)


def test_预测快照只允许追加且当前与历史过期展示语义不同() -> None:
    """相同快照不得覆盖；当前过期须拒绝，历史过期须标示生成时点后可回看。"""

    store = PredictionSnapshotStore()
    snapshot = store.append(
        snapshot_id="prediction:NASDAQ:AAPL:2026-07-14T09:30:00Z",
        prediction_input=PredictionInput(**完整预测输入()),
        prediction_output=PredictionOutput(**完整预测输出()),
    )

    with pytest.raises(ImmutablePredictionSnapshotError, match="覆盖"):
        store.append(
            snapshot_id=snapshot.snapshot_id,
            prediction_input=PredictionInput(**完整预测输入()),
            prediction_output=PredictionOutput(**完整预测输出()),
        )

    assert snapshot.display_state_for_current_data("STALE") is PredictionDisplayState.CURRENT_UNAVAILABLE
    assert snapshot.display_state_for_history() is PredictionDisplayState.HISTORICAL_SNAPSHOT
    assert snapshot.generated_at == datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
