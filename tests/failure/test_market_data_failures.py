"""验证新浪代码规则拒绝不安全或不受支持的身份。"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from stock_agent.adapters.market_data.sina_adapter import SinaDataSourceError, SinaHttpAdapter
from stock_agent.adapters.market_data.sina_codes import (
    UnsupportedSinaCodeError,
    normalize_sina_code,
)
from stock_agent.application.versioning_service import ImmutableVersionError, VersioningService
from stock_agent.domain.freshness import (
    FreshnessClassificationError,
    require_usable_for_current_prediction,
)
from stock_agent.domain.market import (
    InstrumentIdentity,
    InstrumentIdentityInput,
    Market,
    MarketRuleError,
)
from stock_agent.domain.market_rules import CompanyAction


class 忽略事实记录器:
    """隔离响应校验测试的记录端口，不替代持久化集成测试。"""

    def record(self, raw_response: bytes, quotes: list[object]) -> None:
        """响应校验失败路径不会调用该端口。"""


def 新浪响应(日期: str, 时间: str) -> bytes:
    """构造字段数量完整的单条新浪响应，供失败边界覆盖使用。"""

    fields = ["浦发银行", "10.00", "10.10", "10.25", *("0" for _ in range(26)), 日期, 时间, "00"]
    return f'var hq_str_sh600000="{",".join(fields)}";'.encode("gbk")


@pytest.mark.parametrize(
    ("exchange", "display_code", "expected"),
    [("SSE", "600000", "sh600000"), ("SZSE", "000001", "sz000001")],
)
def test_新浪代码规范化支持沪深交易所(exchange: str, display_code: str, expected: str) -> None:
    """新浪 A 股请求代码必须携带正确交易所前缀。"""

    identity = InstrumentIdentity(Market.CN, exchange, display_code, "CNY")

    assert normalize_sina_code(identity) == expected


@pytest.mark.parametrize(
    "identity",
    [
        InstrumentIdentity(Market.HK, "HKEX", "00001", "HKD"),
        InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD"),
    ],
)
def test_新浪代码规范化拒绝不支持的有效市场(identity: InstrumentIdentity) -> None:
    """其他市场的有效证券身份也不得进入仅支持 A 股的新浪代码边界。"""

    with pytest.raises(UnsupportedSinaCodeError):
        normalize_sina_code(identity)


@pytest.mark.parametrize(
    "raw_identity",
    [
        InstrumentIdentityInput(Market.CN, "BSE", "830000", "CNY"),
        InstrumentIdentityInput(Market.CN, "SSE", "60000", "CNY"),
        InstrumentIdentityInput(Market.CN, "SZSE", "0000A1", "CNY"),
        InstrumentIdentityInput(Market.CN, "SSE", "１２３４５６", "CNY"),
    ],
)
def test_原始证券输入转换拒绝跨市场交易所和非法代码(
    raw_identity: InstrumentIdentityInput,
) -> None:
    """失败场景先以原始输入记录，转换为公开证券身份时再统一拒绝。"""

    with pytest.raises(MarketRuleError):
        raw_identity.to_identity()


def test_原始证券输入转换拒绝非正式市场标识() -> None:
    """原始接口的字符串市场标识不能绕过正式枚举和证券身份规则。"""

    raw_identity = InstrumentIdentityInput("CN", "SSE", "600000", "CNY")  # type: ignore[arg-type]

    with pytest.raises(MarketRuleError, match="市场"):
        raw_identity.to_identity()


@pytest.mark.parametrize("codes", [[], ["600000"], ["sh60000"], ["xx600000"], ["sh６０００００"]])
def test_新浪适配器拒绝空或非法请求代码(codes: list[str], local_data_root: Path) -> None:
    """请求代码必须已是沪深前缀加六码 ASCII 数字，避免构造越界地址。"""

    with pytest.raises(SinaDataSourceError):
        SinaHttpAdapter(
            lambda _url: b"", 忽略事实记录器(), VersioningService(local_data_root)
        ).fetch_quotes(codes, datetime.now(UTC))


@pytest.mark.parametrize(
    "response",
    [
        RuntimeError("网络故障"),
        b"\xff",
        'var hq_str_sh600000="浦发银行,10.00";'.encode("gbk"),
        'var hq_str_sh600000="浦发银行,abc,10.10,无效";'.encode("gbk"),
        新浪响应("2026-02-30", "09:30:00"),
        新浪响应("2026-07-14", "25:30:00"),
    ],
)
def test_新浪适配器拒绝异常或不完整响应且不返回部分行情(
    response: bytes | Exception, local_data_root: Path
) -> None:
    """读取、解码、字段和市场时间任一异常都必须作为数据源错误整体失败。"""

    def 读取行情(_url: str) -> bytes:
        if isinstance(response, Exception):
            raise response
        return response

    with pytest.raises(SinaDataSourceError):
        SinaHttpAdapter(
            读取行情, 忽略事实记录器(), VersioningService(local_data_root)
        ).fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, tzinfo=UTC))


def test_新浪适配器响应缺少任一请求代码时拒绝全部行情(local_data_root: Path) -> None:
    """多证券响应缺行时不能泄露已成功解析的部分结果。"""

    response = 新浪响应("2026-07-14", "09:30:00")

    with pytest.raises(SinaDataSourceError):
        SinaHttpAdapter(
            lambda _url: response, 忽略事实记录器(), VersioningService(local_data_root)
        ).fetch_quotes(["sh600000", "sz000001"], datetime(2026, 7, 14, 1, 30, tzinfo=UTC))


@pytest.mark.parametrize(
    "缺失字段",
    [
        "trading_date",
        "market_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "currency",
        "adjustment_basis",
        "source_id",
        "collected_at",
        "source_data_version",
    ],
)
def test_标准化历史日线缺少任一契约字段时整批拒绝且不产生持久化记录(
    缺失字段: str, local_data_root: Path
) -> None:
    """以公开标准化日线契约校验字段，不依赖特定供应商原始响应位置。"""

    from stock_agent.application.historical_market_data import (
        HistoricalDailyBarBatch,
        HistoricalDailyBarValidationError,
    )

    完整日线 = {
        "security_id": InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
        "trading_date": "2026-07-14",
        "market_time": datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
        "open": 10.0,
        "high": 10.3,
        "low": 9.9,
        "close": 10.2,
        "volume": 1000,
        "currency": "CNY",
        "adjustment_basis": "none",
        "source_id": "test-source",
        "collected_at": datetime(2026, 7, 14, 15, 1, tzinfo=UTC),
        "source_data_version": "daily-v1",
    }
    不完整日线 = 完整日线.copy()
    del 不完整日线[缺失字段]

    批次 = HistoricalDailyBarBatch()
    with pytest.raises(HistoricalDailyBarValidationError, match="缺失|完整"):
        批次.normalize([完整日线, 不完整日线])

    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()


@pytest.mark.parametrize("状态", ["DELAYED", "STALE", "CLOSED"])
def test_当前预测拒绝过期或休市行情并给出不可用原因(状态: str) -> None:
    """当前预测入口必须把不可用原因显式反馈给调用方，不能只返回裸布尔值。"""

    with pytest.raises(FreshnessClassificationError, match="过期|不可用"):
        require_usable_for_current_prediction(
            {
                "state": 状态,
                "market_time": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
                "collected_at": datetime(2026, 7, 14, 9, 16, tzinfo=UTC),
                "time_is_verifiable": True,
            }
        )


def test_当前预测拒绝市场时间不可验证行情并给出不可用原因() -> None:
    """即使状态标为实时，市场时间不可验证也必须明确拒绝当前预测。"""

    with pytest.raises(FreshnessClassificationError, match="不可验证|不可用"):
        require_usable_for_current_prediction(
            {
                "state": "REALTIME",
                "market_time": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
                "collected_at": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
                "time_is_verifiable": False,
            }
        )


@pytest.mark.parametrize(
    ("market", "exchange", "display_code", "currency"),
    [
        (Market.CN, "HKEX", "00001", "CNY"),
        (Market.HK, "NASDAQ", "AAPL", "HKD"),
        (Market.US, "SSE", "600000", "USD"),
        (Market.HK, "HKEX", "00001", "USD"),
    ],
)
def test_证券身份拒绝市场交易所或币种不一致(
    market: Market, exchange: str, display_code: str, currency: str
) -> None:
    """A、H、美股解析不得把相同代码、错误交易所或错误币种猜测为有效证券。"""

    with pytest.raises(ValueError, match="市场|交易所|币种"):
        InstrumentIdentity(market, exchange, display_code, currency)


def test_未带市场标识的非唯一显示代码必须拒绝解析() -> None:
    """同一显示代码存在于多个市场时，查询必须要求调用方提供市场或交易所。"""

    from stock_agent.domain.market import MarketRuleError, resolve_instrument_identity

    候选证券 = [
        InstrumentIdentity(Market.CN, "SZSE", "000001", "CNY"),
        InstrumentIdentity(Market.CN, "SSE", "000001", "CNY"),
    ]

    with pytest.raises(MarketRuleError, match="市场|交易所|非唯一"):
        resolve_instrument_identity(display_code="000001", candidates=候选证券)


@pytest.mark.parametrize("复权比例", [True, False, "1", float("nan"), float("inf"), 0, -1])
def test_公司行动拒绝不合法复权比例(复权比例: float) -> None:
    """复权比例必须为有限正数，不能让无效公司行动进入历史价格计算。"""

    with pytest.raises(ValueError, match="复权比例"):
        CompanyAction(
            action_id="split-20260714",
            action_type="split",
            effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
            version_id="v1",
            source_id="test-source",
            adjustment_ratio=复权比例,
        )


@pytest.mark.parametrize(
    ("action_id", "effective_at"),
    [
        ("", datetime(2026, 7, 14, 9, 0, tzinfo=UTC)),
        ("split-20260714", datetime(2026, 7, 14, 9, 0)),
    ],
)
def test_公司行动拒绝缺失标识或无时区日期(action_id: str, effective_at: datetime) -> None:
    """公司行动的标识和生效时点均是可追溯复权的最小前提。"""

    with pytest.raises(ValueError, match="标识|时区"):
        CompanyAction(
            action_id=action_id,
            action_type="split",
            effective_at=effective_at,
            version_id="v1",
            source_id="test-source",
        )


def test_公司行动拒绝证券所属市场不一致() -> None:
    """公司行动必须绑定与证券身份一致的市场，不能跨市场混用。"""

    with pytest.raises(ValueError, match="证券|市场"):
        CompanyAction(
            action_id="split-20260714",
            action_type="split",
            effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
            version_id="v1",
            source_id="test-source",
            security_id=InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
            market=Market.US,
        )


def test_复权历史研究在公司行动记录缺失时明确拒绝() -> None:
    """缺少应有的公司行动记录时，复权历史研究不能输出看似可用的结果。"""

    from stock_agent.domain.market_rules import (
        PointInTimeViolation,
        require_company_actions_for_adjustment,
    )

    with pytest.raises(PointInTimeViolation, match="公司行动.*缺失|不可用"):
        require_company_actions_for_adjustment(
            security_id=InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
            analysis_time=datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
            actions=[],
        )


@pytest.mark.parametrize(
    "行动证券",
    [
        None,
        InstrumentIdentity(Market.CN, "SSE", "600519", "CNY"),
    ],
)
def test_复权历史研究拒绝未知或不属于目标证券的公司行动(
    行动证券: InstrumentIdentity | None,
) -> None:
    """未知归属和其他证券的行动都不能充当目标证券的复权依据。"""

    from stock_agent.domain.market_rules import (
        PointInTimeViolation,
        require_company_actions_for_adjustment,
    )

    with pytest.raises(PointInTimeViolation, match="证券|归属|不一致|缺失"):
        require_company_actions_for_adjustment(
            security_id=InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
            analysis_time=datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
            actions=[
                CompanyAction(
                    action_id="split-20260714",
                    action_type="split",
                    effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
                    version_id="v1",
                    source_id="test-source",
                    security_id=行动证券,
                )
            ],
        )


def test_复权历史研究拒绝混入其他证券行动的记录集() -> None:
    """混杂行动集不能借由一条目标证券记录绕过跨证券归属审查。"""

    from stock_agent.domain.market_rules import (
        PointInTimeViolation,
        require_company_actions_for_adjustment,
    )

    目标证券 = InstrumentIdentity(Market.CN, "SSE", "600000", "CNY")
    with pytest.raises(PointInTimeViolation, match="证券|不一致"):
        require_company_actions_for_adjustment(
            security_id=目标证券,
            analysis_time=datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
            actions=[
                CompanyAction(
                    action_id="split-target",
                    action_type="split",
                    effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
                    version_id="v1",
                    source_id="test-source",
                    security_id=目标证券,
                ),
                CompanyAction(
                    action_id="split-other",
                    action_type="split",
                    effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
                    version_id="v1",
                    source_id="test-source",
                    security_id=InstrumentIdentity(Market.CN, "SSE", "600519", "CNY"),
                ),
            ],
        )


@pytest.mark.parametrize("dataset", ["market-data-raw", "prediction-snapshots"])
def test_原始行情和预测快照拒绝静默覆盖(dataset: str, local_data_root: Path) -> None:
    """相同版本标识重写必须失败，保留可追溯的既有事实。"""

    service = VersioningService(local_data_root)
    service.commit_bytes(
        dataset=dataset,
        version_id="v1",
        content=b"first",
        source_id="test-source",
    )

    with pytest.raises(ImmutableVersionError):
        service.commit_bytes(
            dataset=dataset,
            version_id="v1",
            content=b"overwrite",
            source_id="test-source",
        )
