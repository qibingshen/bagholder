"""历史日线的最小标准化契约。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from stock_agent.application.versioning_service import VersioningService
from stock_agent.domain.market import InstrumentIdentity, Market


class HistoricalDailyBarValidationError(ValueError):
    """表示历史日线未满足完整、可追溯的标准化契约。"""


@dataclass(frozen=True, slots=True)
class HistoricalDailyBar:
    """已标准化的一条历史日线，明确不能作为实时行情使用。"""

    security_id: InstrumentIdentity
    trade_date: date
    market_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    currency: str
    adjustment_basis: str
    source_id: str
    collected_at: datetime
    data_version: str


class HistoricalDailyBarBatch:
    """对整批历史日线执行先验证、后返回的标准化。"""

    _REQUIRED_FIELDS = {
        "security_id",
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
        "data_version",
    }

    def __init__(self, versioning_service: VersioningService) -> None:
        self._versioning_service = versioning_service

    def normalize_and_save(self, records: list[dict[str, Any]]) -> list[HistoricalDailyBar]:
        """验证完整批次并返回标准化结果；任一记录无效即拒绝整批。"""
        if not records:
            raise HistoricalDailyBarValidationError("历史日线批次不能为空")
        return [self._normalize(record) for record in records]

    def _normalize(self, record: dict[str, Any]) -> HistoricalDailyBar:
        missing = self._REQUIRED_FIELDS - record.keys()
        if missing or any(record[field] in (None, "") for field in self._REQUIRED_FIELDS - missing):
            raise HistoricalDailyBarValidationError("历史日线字段缺失或不完整")

        security_id = record["security_id"]
        if not isinstance(security_id, InstrumentIdentity) or security_id.market is not Market.CN:
            raise HistoricalDailyBarValidationError("历史日线证券身份必须属于 CN 市场")
        if record["currency"] != security_id.currency:
            raise HistoricalDailyBarValidationError("历史日线币种与证券身份不一致")
        if not isinstance(record["source_id"], str) or not record["source_id"].strip():
            raise HistoricalDailyBarValidationError("历史日线来源无效")

        market_time = self._datetime(record["market_time"], "市场时间")
        collected_at = self._datetime(record["collected_at"], "采集时间")
        if market_time > collected_at:
            raise HistoricalDailyBarValidationError("市场时间不能晚于采集时间")
        try:
            trade_date = date.fromisoformat(str(record["trading_date"]))
        except (TypeError, ValueError) as error:
            raise HistoricalDailyBarValidationError("交易日无效") from error

        open_price = self._number(record["open"], "开盘价")
        high = self._number(record["high"], "最高价")
        low = self._number(record["low"], "最低价")
        close = self._number(record["close"], "收盘价")
        volume = self._number(record["volume"], "成交量")
        if low > min(open_price, close) or high < max(open_price, close) or high < low:
            raise HistoricalDailyBarValidationError("日线价格区间无效")
        if volume < 0:
            raise HistoricalDailyBarValidationError("成交量不能为负数")
        if (
            not isinstance(record["adjustment_basis"], str)
            or not record["adjustment_basis"].strip()
        ):
            raise HistoricalDailyBarValidationError("复权口径无效")
        if not isinstance(record["data_version"], str) or not record["data_version"].strip():
            raise HistoricalDailyBarValidationError("数据版本无效")

        return HistoricalDailyBar(
            security_id=security_id,
            trade_date=trade_date,
            market_time=market_time,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            currency=record["currency"],
            adjustment_basis=record["adjustment_basis"],
            source_id=record["source_id"],
            collected_at=collected_at,
            data_version=record["data_version"],
        )

    @staticmethod
    def _datetime(value: Any, label: str) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HistoricalDailyBarValidationError(f"{label}必须包含时区")
        return value

    @staticmethod
    def _number(value: Any, label: str) -> float:
        if isinstance(value, bool):
            raise HistoricalDailyBarValidationError(f"{label}无效")
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise HistoricalDailyBarValidationError(f"{label}无效") from error
        if not math.isfinite(number):
            raise HistoricalDailyBarValidationError(f"{label}无效")
        return number
