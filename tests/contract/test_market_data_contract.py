"""验证行情适配器协议与注册表不依赖具体供应商。"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_agent.adapters.market_data.base import (
    MarketDataAdapter,
    NormalizedQuote,
    SourceCapability,
)
from stock_agent.adapters.market_data.registry import (
    DuplicateSourceError,
    MarketDataRegistry,
    SourceCapabilityViolationError,
    UnknownSourceError,
)
from stock_agent.application.market_service import (
    HistoricalDailyBar,
    InstrumentCatalogEntry,
    MarketService,
    MarketStatus,
)
from stock_agent.contracts.common import Freshness
from stock_agent.desktop.viewmodels.security_view_model import (
    IndicatorFact,
    RelativeStrengthFact,
    SectorMembershipFact,
    SecurityResearchViewModel,
)
from stock_agent.domain.market import InstrumentIdentity, InstrumentIdentityInput, Market


def 市场证券身份(market: Market) -> InstrumentIdentity:
    """构造仅用于契约测试的完整证券身份。"""

    exchange, display_code, currency = {
        Market.CN: ("SSE", "600000", "CNY"),
        Market.HK: ("HKEX", "00700", "HKD"),
        Market.US: ("NASDAQ", "AAPL", "USD"),
    }[market]
    return InstrumentIdentity(
        market=market,
        exchange=exchange,
        display_code=display_code,
        currency=currency,
    )


class 演示行情适配器:
    """用于验证注册表的最小适配器，不连接任何外部服务。"""

    capability = SourceCapability(
        source_id="演示来源",
        markets=("CN",),
        credential_required=False,
        supports_realtime=True,
    )

    def fetch_quotes(self, codes: list[str], collected_at: datetime) -> list[NormalizedQuote]:
        """返回空结果，避免测试引入供应商实现。"""

        return []


def test_注册表可以注册并按来源标识获取适配器() -> None:
    """核心服务只通过通用协议和来源标识访问行情适配器。"""

    registry = MarketDataRegistry()
    adapter: MarketDataAdapter = 演示行情适配器()

    registry.register(adapter)

    assert registry.get("演示来源") is adapter


def test_注册表拒绝重复来源标识() -> None:
    """同一来源只能注册一次，避免运行时覆盖已选定的行情来源。"""

    registry = MarketDataRegistry()
    registry.register(演示行情适配器())

    with pytest.raises(DuplicateSourceError, match="演示来源"):
        registry.register(演示行情适配器())


def test_注册表拒绝未知来源标识() -> None:
    """请求未知来源时返回明确领域错误，而不是泄漏字典实现细节。"""

    with pytest.raises(UnknownSourceError, match="未知来源"):
        MarketDataRegistry().get("未知来源")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("market_time", None),
        ("collected_at", None),
        ("data_version", ""),
    ],
)
def test_规范化行情拒绝缺少关键时间或数据版本(field: str, value: datetime | str | None) -> None:
    """缺少市场时间、采集时间或版本的供应商数据不能构造成统一行情。"""

    quote = {
        "security_id": 市场证券身份(Market.CN),
        "price": 10.25,
        "source_id": "演示来源",
        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
        "data_version": "演示版本-1",
        "freshness": Freshness(state="REALTIME", age_seconds=1),
    }
    quote[field] = value

    with pytest.raises(ValidationError):
        NormalizedQuote(**quote)


@pytest.mark.parametrize("field", ["market_time", "collected_at"])
def test_规范化行情拒绝不带时区的时间(field: str) -> None:
    """行情时间必须含时区，避免跨市场比较时把本地时间误认为同一时点。"""

    quote = {
        "security_id": 市场证券身份(Market.CN),
        "price": 10.25,
        "source_id": "演示来源",
        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
        "data_version": "演示版本-1",
        "freshness": Freshness(state="REALTIME", age_seconds=1),
    }
    quote[field] = datetime(2026, 7, 14, 9, 30)

    with pytest.raises(ValidationError):
        NormalizedQuote(**quote)


def test_规范化行情拒绝缺少单条行情新鲜度() -> None:
    """每条行情必须带有新鲜度，供核心服务在使用前执行时效性控制。"""

    with pytest.raises(ValidationError, match="freshness"):
        NormalizedQuote(
            security_id=市场证券身份(Market.CN),
            price=10.25,
            source_id="演示来源",
            market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
            data_version="演示版本-1",
        )


def test_规范化行情接受严格的新鲜度状态() -> None:
    """行情新鲜度使用现有公共契约，避免各来源自定义不兼容状态。"""

    quote = NormalizedQuote(
        security_id=市场证券身份(Market.CN),
        price=10.25,
        source_id="演示来源",
        market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
        data_version="演示版本-1",
        freshness=Freshness(state="REALTIME", age_seconds=1),
    )

    assert quote.freshness.state == "REALTIME"


def test_来源能力拒绝空市场范围() -> None:
    """来源必须明确声明至少一个覆盖市场，避免注册不可用的适配器。"""

    with pytest.raises(ValidationError, match="markets"):
        SourceCapability(
            source_id="演示来源",
            markets=(),
            credential_required=False,
            supports_realtime=True,
        )


@pytest.mark.parametrize(
    ("market", "age_seconds"),
    [(Market.CN, 6), (Market.HK, 16), (Market.US, 16)],
)
def test_规范化行情拒绝超过市场实时年龄上限(market: Market, age_seconds: int) -> None:
    """实时行情超过所属市场上限时，不能进入统一行情契约。"""

    with pytest.raises(ValidationError, match="实时行情"):
        NormalizedQuote(
            security_id=市场证券身份(market),
            price=10.25,
            source_id="演示来源",
            market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            collected_at=datetime(2026, 7, 14, 9, 30, age_seconds, tzinfo=UTC),
            data_version="演示版本-1",
            freshness=Freshness(state="REALTIME", age_seconds=age_seconds),
        )


@pytest.mark.parametrize(
    ("market", "age_seconds"),
    [(Market.CN, 5), (Market.HK, 15), (Market.US, 15)],
)
def test_规范化行情接受市场实时年龄上限内的行情(market: Market, age_seconds: int) -> None:
    """实时行情等于所属市场上限时仍是合法可用的行情。"""

    quote = NormalizedQuote(
        security_id=市场证券身份(market),
        price=10.25,
        source_id="演示来源",
        market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        collected_at=datetime(2026, 7, 14, 9, 30, age_seconds, tzinfo=UTC),
        data_version="演示版本-1",
        freshness=Freshness(state="REALTIME", age_seconds=age_seconds),
    )

    assert quote.freshness.age_seconds == age_seconds


def test_规范化行情拒绝与时点计算不一致的新鲜度年龄() -> None:
    """供应商不能把过期行情填成较小年龄以伪装为实时。"""

    with pytest.raises(ValidationError, match="年龄"):
        NormalizedQuote(
            security_id=市场证券身份(Market.CN),
            price=10.25,
            source_id="演示来源",
            market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            collected_at=datetime(2026, 7, 14, 9, 30, 6, tzinfo=UTC),
            data_version="演示版本-1",
            freshness=Freshness(state="REALTIME", age_seconds=1),
        )


@pytest.mark.parametrize(
    ("age_seconds", "forged_state"),
    [
        (61, "NEAR_REALTIME"),
        (901, "DELAYED"),
        (3600, "NEAR_REALTIME"),
    ],
)
def test_规范化行情拒绝非休市状态伪造的新鲜度状态(age_seconds: int, forged_state: str) -> None:
    """非休市行情必须由真实市场时间严格推导状态，不能借低等级状态伪装延迟。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)

    with pytest.raises(ValidationError, match="状态"):
        NormalizedQuote(
            security_id=市场证券身份(Market.CN),
            price=10.25,
            source_id="演示来源",
            market_time=collected_at - timedelta(seconds=age_seconds),
            collected_at=collected_at,
            data_version="演示版本-1",
            freshness=Freshness(state=forged_state, age_seconds=age_seconds),
        )


def test_规范化行情使用统一的向上取整年龄计算微秒时点() -> None:
    """含微秒的采集间隔应统一向上取整，避免适配器与统一模型产生不同年龄。"""

    market_time = datetime(2026, 7, 14, 9, 30, microsecond=123456, tzinfo=UTC)
    quote = NormalizedQuote(
        security_id=市场证券身份(Market.CN),
        price=10.25,
        source_id="演示来源",
        market_time=market_time,
        collected_at=market_time + timedelta(seconds=3, microseconds=1),
        data_version="演示版本-1",
        freshness=Freshness(state="REALTIME", age_seconds=4),
    )

    assert quote.freshness.age_seconds == 4


def test_规范化行情拒绝未来市场时间() -> None:
    """未来市场时间不能借由非实时状态绕过事实时点边界。"""

    with pytest.raises(ValidationError, match="不能晚于"):
        NormalizedQuote(
            security_id=市场证券身份(Market.CN),
            price=10.25,
            source_id="演示来源",
            market_time=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            data_version="演示版本-1",
            freshness=Freshness(state="CLOSED", age_seconds=0),
        )


@pytest.mark.parametrize(
    "returned_source, returned_market", [("其他来源", Market.CN), ("演示来源", Market.US)]
)
def test_注册表拒绝与所选来源能力不一致的整批行情(
    returned_source: str, returned_market: Market
) -> None:
    """注册表必须拒绝来源或市场不一致的整批返回，不能泄露部分报价。"""

    class 越界适配器(演示行情适配器):
        def fetch_quotes(self, codes: list[str], collected_at: datetime) -> list[NormalizedQuote]:
            return [
                NormalizedQuote(
                    security_id=市场证券身份(returned_market),
                    price=10.25,
                    source_id=returned_source,
                    market_time=collected_at,
                    collected_at=collected_at,
                    data_version="演示版本-1",
                    freshness=Freshness(state="REALTIME", age_seconds=0),
                )
            ]

    registry = MarketDataRegistry()
    registry.register(越界适配器())

    with pytest.raises(SourceCapabilityViolationError):
        registry.fetch_quotes(
            "演示来源", ["600000"], datetime(2026, 7, 14, 9, 30, tzinfo=UTC), Market.CN
        )


@pytest.mark.parametrize("market", [Market.CN, Market.HK, Market.US])
def test_市场状态查询返回跨市场必填时点与来源字段(market: Market) -> None:
    """A股、港股和美股状态均应包含可审计的市场时点、采集时点、来源及新鲜度。"""

    status = MarketService().get_market_status(market)

    assert isinstance(status, MarketStatus)
    assert status.market is market
    assert status.market_timezone
    assert status.trading_calendar_status
    assert status.market_time.tzinfo is not None
    assert status.collected_at.tzinfo is not None
    assert status.source_id
    assert status.freshness is not None


@pytest.mark.parametrize("field", ["market_time", "collected_at"])
def test_市场状态拒绝缺失市场时点或采集时点(field: str) -> None:
    """缺少市场时点或采集时点的状态不可用于展示或后续决策。"""

    payload = {
        "market": Market.CN,
        "market_timezone": "Asia/Shanghai",
        "trading_calendar_status": "OPEN",
        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
        "source_id": "契约来源",
        "freshness": Freshness(state="REALTIME", age_seconds=1),
    }
    payload[field] = None

    with pytest.raises(ValidationError):
        MarketStatus(**payload)


def test_市场状态查询拒绝缺少传入的本地日历事实() -> None:
    """调用方显式提供空本地日历时，服务不得回退到内置样例掩盖数据缺失。"""

    with pytest.raises(ValueError, match="缺少.*日历状态|采集时间"):
        MarketService(market_statuses=[]).get_market_status(Market.CN)


def test_证券目录查询返回身份来源时点和版本() -> None:
    """目录身份必须能追溯到本地事实来源、采集时间和版本，不能只返回裸代码。"""

    entry = MarketService().get_instrument_catalog_entry("600000", market=Market.CN)

    assert isinstance(entry, InstrumentCatalogEntry)
    assert entry.security_id == 市场证券身份(Market.CN)
    assert entry.source_id
    assert entry.collected_at.tzinfo is not None
    assert entry.data_version


def test_证券目录解析入口返回完整可追溯目录事实() -> None:
    """解析入口不得将目录事实降级为无法审计的裸证券身份。"""

    entry = MarketService().resolve_security_identity("600000", market=Market.CN)

    assert isinstance(entry, InstrumentCatalogEntry)
    assert entry.security_id == 市场证券身份(Market.CN)
    assert entry.source_id
    assert entry.collected_at.tzinfo is not None
    assert entry.data_version


@pytest.mark.parametrize("market", [Market.CN, Market.HK, Market.US])
def test_市场状态市场时间绑定到对应的_IANA_时区(market: Market) -> None:
    """市场状态的市场时间必须携带所属市场的 IANA 时区，而非仅相同 UTC 偏移。"""

    status = MarketService().get_market_status(market)

    assert isinstance(status.market_time.tzinfo, ZoneInfo)
    assert status.market_time.tzinfo.key == market.timezone


def test_市场状态拒绝仅有相同偏移的非市场_IANA_时区() -> None:
    """市场状态不得用 UTC 或固定偏移替代所属市场 IANA 时区。"""

    with pytest.raises(ValidationError, match="市场时间.*时区"):
        MarketStatus(
            market=Market.CN,
            market_timezone="Asia/Shanghai",
            trading_calendar_status="OPEN",
            market_time=datetime(2026, 7, 14, 1, 30, tzinfo=UTC),
            collected_at=datetime(2026, 7, 14, 1, 30, 1, tzinfo=UTC),
            source_id="合同来源",
            data_version="日历版本-1",
            freshness=Freshness(state="REALTIME", age_seconds=1),
        )


def test_历史日线拒绝市场时间不是证券所属_IANA_时区() -> None:
    """UTC 时间戳不能替代日线所属市场的本地交易时点。"""

    payload = 历史日线有效载荷()
    payload["market_time"] = datetime(2026, 7, 13, 7, 0, tzinfo=UTC)

    with pytest.raises(ValidationError, match="市场时间.*时区"):
        HistoricalDailyBar(**payload)


def test_历史日线拒绝交易日与市场本地日期不一致() -> None:
    """跨日 UTC 换算不得让日线交易日和所属市场本地日期错位。"""

    payload = 历史日线有效载荷()
    payload["market_time"] = datetime(2026, 7, 14, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    with pytest.raises(ValidationError, match="交易日.*市场时间"):
        HistoricalDailyBar(**payload)


def test_显式空证券目录不回退内置样例() -> None:
    """调用方声明本地目录缺失时，查询必须返回明确缺失而不是样例证券。"""

    with pytest.raises(ValueError, match="目录.*不存在|匹配"):
        MarketService(instruments=[]).resolve_security_identity("600000", market=Market.CN)


def test_历史日线包含可追溯字段且不得标为实时() -> None:
    """历史日线应保留身份、复权、币种、来源和版本信息，且不能伪装为实时行情。"""

    bar = HistoricalDailyBar(
        security_id=市场证券身份(Market.CN),
        trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
        open=10.0,
        high=10.5,
        low=9.8,
        close=10.2,
        volume=1_000_000,
        adjustment_basis="NONE",
        currency="CNY",
        source_id="契约来源",
        market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        data_version="日线版本-1",
        freshness=Freshness(state="CLOSED", age_seconds=0),
    )

    assert bar.security_id.market is Market.CN
    assert bar.trade_date.isoformat() == "2026-07-13"
    assert bar.adjustment_basis == "NONE"
    assert bar.freshness.state != "REALTIME"


def test_历史日线拒绝实时新鲜度标记() -> None:
    """历史日线不得以实时新鲜度状态绕过数据时点边界。"""

    with pytest.raises(ValidationError):
        HistoricalDailyBar(
            security_id=市场证券身份(Market.CN),
            trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
            open=10.0,
            high=10.5,
            low=9.8,
            close=10.2,
            volume=1_000_000,
            adjustment_basis="NONE",
            currency="CNY",
            source_id="契约来源",
            market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            data_version="日线版本-1",
            freshness=Freshness(state="REALTIME", age_seconds=0),
        )


def test_历史日线查询拒绝倒置日期范围() -> None:
    """查询起始日期晚于结束日期时必须拒绝，避免返回含义不明的数据集。"""

    with pytest.raises(ValueError):
        MarketService().get_historical_daily_bars(
            市场证券身份(Market.CN),
            start_date=datetime(2026, 7, 14, tzinfo=UTC).date(),
            end_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
        )


def test_历史日线查询拒绝跨市场不匹配证券代码() -> None:
    """美股身份不得使用A股六码代码，服务必须在查询边界拒绝跨市场代码。"""

    cross_market_security = InstrumentIdentityInput(
        market=Market.US,
        exchange="NASDAQ",
        display_code="600000",
        currency="USD",
    )

    with pytest.raises(ValueError):
        MarketService().get_historical_daily_bars(
            cross_market_security,
            start_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
            end_date=datetime(2026, 7, 14, tzinfo=UTC).date(),
        )


def 历史日线有效载荷() -> dict[str, object]:
    """构造完整历史日线载荷，供字段保留和拒绝场景共用。"""

    return {
        "security_id": 市场证券身份(Market.CN),
        "trade_date": datetime(2026, 7, 13, tzinfo=UTC).date(),
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "volume": 1_000_000,
        "adjustment_basis": "NONE",
        "currency": "CNY",
        "source_id": "契约来源",
        "market_time": datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        "collected_at": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        "data_version": "日线版本-1",
        "freshness": Freshness(state="CLOSED", age_seconds=0),
    }


def test_历史日线成功结果逐字段原样保留() -> None:
    """服务模型不得在规范化时丢失、重写或推断历史日线的审计字段。"""

    payload = 历史日线有效载荷()
    bar = HistoricalDailyBar(**payload)

    assert bar.security_id == payload["security_id"]
    assert bar.security_id.market is Market.CN
    assert bar.trade_date == payload["trade_date"]
    assert bar.open == payload["open"]
    assert bar.high == payload["high"]
    assert bar.low == payload["low"]
    assert bar.close == payload["close"]
    assert bar.volume == payload["volume"]
    assert bar.adjustment_basis == payload["adjustment_basis"]
    assert bar.currency == payload["currency"]
    assert bar.source_id == payload["source_id"]
    assert bar.market_time == payload["market_time"]
    assert bar.collected_at == payload["collected_at"]
    assert bar.data_version == payload["data_version"]
    assert bar.freshness == payload["freshness"]


@pytest.mark.parametrize(
    "field",
    [
        "security_id",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adjustment_basis",
        "currency",
        "source_id",
        "market_time",
        "collected_at",
        "data_version",
        "freshness",
    ],
)
def test_历史日线拒绝缺失任何必填字段(field: str) -> None:
    """历史日线的每个审计、价格和时点字段均为必填，不能使用默认值补齐。"""

    payload = 历史日线有效载荷()
    payload.pop(field)

    with pytest.raises(ValidationError):
        HistoricalDailyBar(**payload)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("security_id", None),
        ("trade_date", None),
        ("open", None),
        ("high", None),
        ("low", None),
        ("close", None),
        ("volume", None),
        ("adjustment_basis", ""),
        ("currency", ""),
        ("source_id", ""),
        ("market_time", None),
        ("collected_at", None),
        ("data_version", ""),
        ("freshness", None),
    ],
)
def test_历史日线拒绝必填字段空值(field: str, invalid_value: object) -> None:
    """空值不能替代历史日线的必填字段，确保结果可追溯且可比较。"""

    payload = 历史日线有效载荷()
    payload[field] = invalid_value

    with pytest.raises(ValidationError):
        HistoricalDailyBar(**payload)


@pytest.mark.parametrize(
    ("market", "expected_timezone", "allowed_calendar_statuses"),
    [
        (Market.CN, "Asia/Shanghai", {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY"}),
        (
            Market.HK,
            "Asia/Hong_Kong",
            {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY", "TYPHOON_SUSPENDED"},
        ),
        (Market.US, "America/New_York", {"OPEN", "CLOSED", "PRE_MARKET", "AFTER_HOURS", "HOLIDAY"}),
    ],
)
def test_各市场状态锁定时区与允许交易日历状态(
    market: Market, expected_timezone: str, allowed_calendar_statuses: set[str]
) -> None:
    """市场状态必须按所属市场返回明确时区和受控的交易日历状态集合。"""

    status = MarketService().get_market_status(market)

    assert status.market is market
    assert status.market_timezone == expected_timezone
    assert status.trading_calendar_status in allowed_calendar_statuses


@pytest.mark.parametrize(
    "security_id",
    [
        InstrumentIdentity(market=Market.CN, exchange="SSE", display_code="600000", currency="CNY"),
        InstrumentIdentity(market=Market.HK, exchange="HKEX", display_code="00700", currency="HKD"),
        InstrumentIdentity(
            market=Market.US, exchange="NASDAQ", display_code="AAPL", currency="USD"
        ),
    ],
)
def test_各市场接受匹配的证券代码(security_id: InstrumentIdentity) -> None:
    """A股、港股和美股的有效代码应通过市场服务的身份边界校验。"""

    assert MarketService().validate_security_identity(security_id) == security_id


@pytest.mark.parametrize(
    "security_id",
    [
        InstrumentIdentityInput(
            market=Market.CN, exchange="SSE", display_code="AAPL", currency="CNY"
        ),
        InstrumentIdentityInput(
            market=Market.HK, exchange="HKEX", display_code="600000", currency="HKD"
        ),
        InstrumentIdentityInput(
            market=Market.US, exchange="NASDAQ", display_code="00700", currency="USD"
        ),
    ],
)
def test_各市场拒绝不符合本市场格式的证券代码(security_id: InstrumentIdentity) -> None:
    """不同市场不得接受另一市场的代码格式，以免跨市场查询串线。"""

    with pytest.raises(ValueError):
        MarketService().validate_security_identity(security_id)


@pytest.mark.parametrize(
    "security_id",
    [
        InstrumentIdentityInput(
            market=Market.CN, exchange="HKEX", display_code="600000", currency="CNY"
        ),
        InstrumentIdentityInput(
            market=Market.HK, exchange="HKEX", display_code="00700", currency="USD"
        ),
        InstrumentIdentityInput(
            market=Market.US, exchange="NASDAQ", display_code="600000", currency="USD"
        ),
    ],
)
def test_市场身份拒绝交易所币种或代码不匹配(security_id: InstrumentIdentity) -> None:
    """市场、交易所、币种和代码必须构成一致身份，任一不匹配均应拒绝。"""

    with pytest.raises(ValueError):
        MarketService().validate_security_identity(security_id)


def _完整日线() -> HistoricalDailyBar:
    """构造带完整本地溯源字段的历史日线事实。"""

    return HistoricalDailyBar(
        security_id=市场证券身份(Market.CN),
        trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
        open=10.0,
        high=10.5,
        low=9.8,
        close=10.2,
        volume=1_000_000,
        adjustment_basis="NONE",
        currency="CNY",
        source_id="本地日线归档",
        market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        data_version="日线版本-7",
        freshness=Freshness(state="CLOSED", age_seconds=0),
    )


def test_证券研究视图保留日线成交量及所有溯源信息() -> None:
    """K线和成交量必须直接展示本地事实，历史数据不可伪装为实时。"""

    bar = _完整日线()
    model = SecurityResearchViewModel.assemble(
        security_id=bar.security_id,
        market_status=MarketService().get_market_status(Market.CN),
        daily_bars=[bar],
    )

    assert model.daily_bars == (bar,)
    assert model.daily_bars[0].volume == 1_000_000
    assert model.daily_bars[0].source_id == "本地日线归档"
    assert model.daily_bars[0].data_version == "日线版本-7"
    assert model.daily_bars[0].freshness.state != "REALTIME"
    assert model.empty_state_zh is None


def test_证券研究视图拒绝缺少溯源版本的指标板块和相对强弱() -> None:
    """缺少来源、时点、输入版本或计算版本的派生事实不得渲染。"""

    with pytest.raises(ValidationError):
        IndicatorFact(
            name="MA5",
            value=10.1,
            source_id="本地指标输入",
            market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            input_data_version="日线版本-7",
            calculation_version="",
        )

    with pytest.raises(ValidationError):
        SectorMembershipFact(
            sector_name="银行",
            source_id="",
            market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            data_version="板块版本-2",
        )

    with pytest.raises(ValidationError):
        RelativeStrengthFact(
            value=0.8,
            benchmark="沪深300",
            source_id="本地相对强弱输入",
            market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            input_data_version="日线版本-7",
            calculation_version="",
        )


@pytest.mark.parametrize("state", ["DELAYED", "STALE", "CLOSED"])
def test_证券研究视图为非实时状态显示中文降级并禁止当前预测(state: str) -> None:
    """延迟、过期或闭市事实必须明确降级，且永不声称实时。"""

    market_time = datetime(2026, 7, 14, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    status = MarketStatus(
        market=Market.CN,
        market_timezone="Asia/Shanghai",
        trading_calendar_status="CLOSED",
        market_time=market_time,
        collected_at=market_time,
        source_id="本地交易日历",
        data_version="日历版本-1",
        freshness=Freshness(state=state, age_seconds=0),
    )

    model = SecurityResearchViewModel.assemble(
        security_id=市场证券身份(Market.CN), market_status=status
    )

    assert model.current_prediction_allowed is False
    assert model.degradation_status_zh
    assert "实时" not in model.degradation_status_zh


def test_证券研究视图在没有日线板块和指标时明确为空状态() -> None:
    """本地事实缺失时展示空状态，不能补造价格、板块或指标数值。"""

    model = SecurityResearchViewModel.assemble(
        security_id=市场证券身份(Market.CN),
        market_status=MarketService().get_market_status(Market.CN),
    )

    assert model.daily_bars == ()
    assert model.indicators == ()
    assert model.sector_membership is None
    assert model.relative_strength is None
    assert model.empty_state_zh


def test_证券研究视图在已验证近实时行情时允许当前预测() -> None:
    """已验证的近实时本地行情应保留当前预测资格，而非被错误降级。"""

    market_time = datetime(2026, 7, 14, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    status = MarketStatus(
        market=Market.CN,
        market_timezone="Asia/Shanghai",
        trading_calendar_status="OPEN",
        market_time=market_time,
        collected_at=market_time,
        source_id="本地交易日历",
        data_version="日历版本-1",
        freshness=Freshness(state="NEAR_REALTIME", age_seconds=0),
    )

    model = SecurityResearchViewModel.assemble(
        security_id=市场证券身份(Market.CN), market_status=status
    )

    assert model.current_prediction_allowed is True
    assert model.degradation_status_zh is None
