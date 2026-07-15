"""按市场日历和时区计算每日任务时点。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

MarketCode = Literal["CN", "HK", "US"]
DailyPhase = Literal["pre_open", "intraday", "post_close"]


@dataclass(frozen=True)
class MarketScheduleConfig:
    """定义单个市场的默认每日任务时间。"""

    market: MarketCode
    timezone: ZoneInfo
    pre_open: time
    intraday: time
    post_close: time

    @classmethod
    def default_for(cls, market: MarketCode) -> MarketScheduleConfig:
        """返回规格确认的三大市场默认时点。"""

        if market == "CN":
            return cls(
                market="CN",
                timezone=ZoneInfo("Asia/Shanghai"),
                pre_open=time(8, 45),
                intraday=time(11, 45),
                post_close=time(15, 30),
            )
        if market == "HK":
            return cls(
                market="HK",
                timezone=ZoneInfo("Asia/Hong_Kong"),
                pre_open=time(8, 45),
                intraday=time(12, 30),
                post_close=time(16, 30),
            )
        return cls(
            market="US",
            timezone=ZoneInfo("America/New_York"),
            pre_open=time(8, 45),
            intraday=time(12, 30),
            post_close=time(16, 30),
        )


@dataclass(frozen=True)
class DailyScheduleRun:
    """每日任务的一个计划运行点。"""

    market: MarketCode
    phase: DailyPhase
    local_time: datetime


class DailyScheduler:
    """根据版本化市场日历和市场时区生成每日任务。"""

    def __init__(
        self,
        configs: list[MarketScheduleConfig],
        holidays: dict[str, set[date]] | None = None,
        half_days: dict[str, dict[date, str]] | None = None,
    ) -> None:
        """注入市场配置、休市日和半日市。"""

        self._configs = tuple(configs)
        self._holidays = holidays or {}
        self._half_days = half_days or {}

    def schedule_for(self, trade_date: date) -> tuple[DailyScheduleRun, ...]:
        """生成指定日期所有市场的开盘前、盘中和收盘后任务。"""

        runs: list[DailyScheduleRun] = []
        for config in self._configs:
            if trade_date in self._holidays.get(config.market, set()):
                continue
            pre_open = config.pre_open
            intraday = config.intraday
            post_close = config.post_close
            half_close = self._half_days.get(config.market, {}).get(trade_date)
            if half_close is not None:
                close_time = _parse_time(half_close)
                intraday = _minus_one_hour(close_time)
                post_close = _plus_minutes(close_time, 30)
            runs.extend(
                (
                    DailyScheduleRun(
                        config.market, "pre_open", _localize(trade_date, pre_open, config.timezone)
                    ),
                    DailyScheduleRun(
                        config.market, "intraday", _localize(trade_date, intraday, config.timezone)
                    ),
                    DailyScheduleRun(
                        config.market,
                        "post_close",
                        _localize(trade_date, post_close, config.timezone),
                    ),
                )
            )
        return tuple(runs)


def _localize(trade_date: date, local_time: time, timezone: ZoneInfo) -> datetime:
    """保留市场本地时区，避免跨平台或夏令时漂移。"""

    return datetime.combine(trade_date, local_time, tzinfo=timezone)


def _parse_time(value: str) -> time:
    """解析半日市提前收盘时间。"""

    hour, minute = value.split(":", maxsplit=1)
    return time(int(hour), int(minute))


def _plus_minutes(value: time, minutes: int) -> time:
    """在同一自然日内给时间增加分钟。"""

    base = datetime.combine(date(2000, 1, 1), value)
    return (base + timedelta(minutes=minutes)).time()


def _minus_one_hour(value: time) -> time:
    """半日市盘中任务安排在提前收盘前一小时。"""

    base = datetime.combine(date(2000, 1, 1), value)
    return (base - timedelta(hours=1)).time()
