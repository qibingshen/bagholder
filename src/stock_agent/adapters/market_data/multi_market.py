"""三市场行情适配器目录、冲突检测、授权降级和限频规则。"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from stock_agent.contracts.common import FreshnessState
from stock_agent.domain.market import Market


class SourceConflictError(ValueError):
    """表示同一市场存在多个未明确优先级的行情来源。"""


class RateLimitExceededError(RuntimeError):
    """表示当前来源超过可审计的请求频率上限。"""


@dataclass(frozen=True, slots=True)
class AdapterDescriptor:
    """描述一个可插拔行情适配器的市场边界和运行约束。"""

    source_id: str
    market: Market
    timezone: str
    currency: str
    requires_credentials: bool
    max_requests_per_minute: int

    @classmethod
    def sina_cn(cls) -> AdapterDescriptor:
        """返回新浪 A 股公开只读适配器描述。"""

        return cls(
            source_id="sina",
            market=Market.CN,
            timezone=Market.CN.timezone,
            currency="CNY",
            requires_credentials=False,
            max_requests_per_minute=60,
        )

    @classmethod
    def hk_delayed(cls) -> AdapterDescriptor:
        """返回港股延迟行情占位适配器描述，后续可替换为授权供应商。"""

        return cls(
            source_id="hk-delayed",
            market=Market.HK,
            timezone=Market.HK.timezone,
            currency="HKD",
            requires_credentials=False,
            max_requests_per_minute=30,
        )

    @classmethod
    def finnhub_us(cls) -> AdapterDescriptor:
        """返回 Finnhub 美股适配器描述，真实调用前必须配置用户自带凭据。"""

        return cls(
            source_id="finnhub",
            market=Market.US,
            timezone=Market.US.timezone,
            currency="USD",
            requires_credentials=True,
            max_requests_per_minute=60,
        )


@dataclass(frozen=True, slots=True)
class AdapterAvailability:
    """描述某市场当前适配器是否可提供行情。"""

    source_id: str
    market: Market
    available: bool
    freshness_state: FreshnessState
    reason_code: str | None
    message_zh: str


class SourceConflictResolver:
    """在进入行情请求前拒绝同市场多来源自动合并。"""

    def select_primary(
        self,
        market: Market,
        descriptors: tuple[AdapterDescriptor, ...],
    ) -> AdapterDescriptor:
        """选择唯一来源；存在多个候选来源时要求上层显式决策。"""

        candidates = tuple(item for item in descriptors if item.market is market)
        if not candidates:
            raise SourceConflictError(f"市场缺少行情来源：{market.value}")
        if len(candidates) > 1:
            raise SourceConflictError(f"来源冲突：{market.value}")
        return candidates[0]


class RateLimiter:
    """按来源记录一分钟窗口内请求次数。"""

    def __init__(self, max_requests_per_minute: int) -> None:
        """初始化限频器，窗口只保存必要时间戳。"""

        if max_requests_per_minute <= 0:
            raise ValueError("限频上限必须大于零")
        self._max_requests_per_minute = max_requests_per_minute
        self._events: dict[str, deque[datetime]] = defaultdict(deque)

    def record(self, source_id: str, occurred_at: datetime) -> None:
        """记录一次请求；超过上限时拒绝整个批次。"""

        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("限频时间必须包含时区")
        events = self._events[source_id]
        window_start = occurred_at - timedelta(minutes=1)
        while events and events[0] <= window_start:
            events.popleft()
        if len(events) >= self._max_requests_per_minute:
            raise RateLimitExceededError(f"来源 {source_id} 触发限频")
        events.append(occurred_at)


class MultiMarketAdapterCatalog:
    """维护 A 股、港股和美股的默认行情来源目录。"""

    def __init__(self, descriptors: tuple[AdapterDescriptor, ...]) -> None:
        """绑定描述符并在启动阶段检查同市场来源冲突。"""

        self._descriptors = descriptors
        resolver = SourceConflictResolver()
        self._primary = {
            market: resolver.select_primary(market, descriptors)
            for market in (Market.CN, Market.HK, Market.US)
        }

    @classmethod
    def default(cls) -> MultiMarketAdapterCatalog:
        """返回首个正式版本的三市场默认适配器目录。"""

        return cls(
            (
                AdapterDescriptor.sina_cn(),
                AdapterDescriptor.hk_delayed(),
                AdapterDescriptor.finnhub_us(),
            )
        )

    def primary_for(self, market: Market) -> AdapterDescriptor:
        """返回指定市场的主适配器描述。"""

        return self._primary[market]

    def availability_for(
        self,
        market: Market,
        authorized_sources: frozenset[str],
    ) -> AdapterAvailability:
        """根据授权状态返回可展示的新鲜度和降级说明。"""

        descriptor = self.primary_for(market)
        if descriptor.requires_credentials and descriptor.source_id not in authorized_sources:
            return AdapterAvailability(
                source_id=descriptor.source_id,
                market=market,
                available=False,
                freshness_state="STALE",
                reason_code="CREDENTIAL_REQUIRED",
                message_zh=f"{descriptor.source_id.title()} 需要用户自带合法凭据，当前已降级。",
            )
        return AdapterAvailability(
            source_id=descriptor.source_id,
            market=market,
            available=True,
            freshness_state="NEAR_REALTIME",
            reason_code=None,
            message_zh="行情来源可用，仍需按市场时间展示新鲜度。",
        )
