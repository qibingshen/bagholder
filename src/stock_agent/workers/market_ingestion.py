"""通过注入读取器采集并原子保存中国市场历史日线。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from stock_agent.application.historical_market_data import (
    HistoricalDailyBar,
    HistoricalDailyBarBatch,
    HistoricalDailyBarValidationError,
)
from stock_agent.application.versioning_service import VersioningService
from stock_agent.domain.market import InstrumentIdentity, Market


class HistoricalDailyIngestionError(RuntimeError):
    """表示历史日线读取、验证或保存失败，且整个批次已回滚。"""


@dataclass(frozen=True, slots=True)
class HistoricalFreshness:
    """历史数据的新鲜度标识，明确排除实时用途。"""

    state: str = "HISTORICAL"


@dataclass(frozen=True, slots=True)
class IngestedHistoricalDailyBar(HistoricalDailyBar):
    """附带历史用途标识的标准化日线。"""

    freshness: HistoricalFreshness = HistoricalFreshness()


@dataclass(frozen=True, slots=True)
class HistoricalDailyIngestionResult:
    """一次可回读历史日线采集的版本链。"""

    bars: list[IngestedHistoricalDailyBar]
    raw_version_id: str
    normalized_version_id: str


class HistoricalDailyIngestionWorker:
    """仅协调注入读取器与同一版本服务，不发起任何网络请求。"""

    def __init__(
        self,
        *,
        read_historical_daily: Callable[..., bytes],
        versioning_service: VersioningService,
    ) -> None:
        self._read_historical_daily = read_historical_daily
        self._versioning_service = versioning_service

    def collect_and_save(
        self,
        *,
        collected_at: datetime,
        security_id: InstrumentIdentity,
        source_id: str,
    ) -> HistoricalDailyIngestionResult:
        """读取注入响应，验证整批后保存原始和标准化工件。"""
        raw_version_id = f"raw-{uuid4().hex}"
        normalized_version_id = f"normalized-{uuid4().hex}"
        try:
            self._validate_request(collected_at, security_id, source_id)
            raw_response = self._read_historical_daily(
                collected_at=collected_at, security_id=security_id, source_id=source_id
            )
            payload = self._parse_payload(raw_response, collected_at, security_id, source_id)
            normalized_content, bars = self._normalize_payload(
                payload, collected_at, security_id, source_id, normalized_version_id
            )
            self._versioning_service.commit_batch(
                batch_id=f"historical-daily-{uuid4().hex}",
                items=[
                    {
                        "dataset": "market-data-raw",
                        "version_id": raw_version_id,
                        "content": raw_response,
                    },
                    {
                        "dataset": "market-data-normalized",
                        "version_id": normalized_version_id,
                        "content": normalized_content,
                        "parent_version_id": raw_version_id,
                    },
                ],
            )
        except HistoricalDailyIngestionError:
            self._rollback(raw_version_id, normalized_version_id)
            raise
        except Exception as error:
            self._rollback(raw_version_id, normalized_version_id)
            raise HistoricalDailyIngestionError(str(error)) from error
        return HistoricalDailyIngestionResult(bars, raw_version_id, normalized_version_id)

    @staticmethod
    def _validate_request(
        collected_at: datetime, security_id: InstrumentIdentity, source_id: str
    ) -> None:
        if source_id != "sina":
            raise HistoricalDailyIngestionError("历史日线来源必须为 sina")
        if security_id.market is not Market.CN:
            raise HistoricalDailyIngestionError("历史日线市场必须为 CN")
        if collected_at.tzinfo is None or collected_at.utcoffset() is None:
            raise HistoricalDailyIngestionError("采集时间必须包含时区")

    @staticmethod
    def _parse_payload(
        raw_response: bytes,
        collected_at: datetime,
        security_id: InstrumentIdentity,
        source_id: str,
    ) -> dict[str, Any]:
        if not isinstance(raw_response, bytes):
            raise HistoricalDailyIngestionError("历史日线读取器必须返回字节")
        try:
            payload = json.loads(raw_response)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HistoricalDailyIngestionError("历史日线原始响应无法解析") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), list):
            raise HistoricalDailyIngestionError("历史日线响应缺少完整 bars 字段")
        expected_identity = {
            "security_code": security_id.display_code,
            "exchange": security_id.exchange,
            "currency": security_id.currency,
            "market": security_id.market.value,
        }
        if payload.get("source_id") != source_id:
            raise HistoricalDailyIngestionError("历史日线来源不一致")
        for field, expected_value in expected_identity.items():
            if payload.get(field) != expected_value:
                raise HistoricalDailyIngestionError(f"历史日线{field}与证券身份不一致")
        if payload.get("collected_at") != collected_at.isoformat():
            raise HistoricalDailyIngestionError("历史日线采集时间不一致")
        if (
            not isinstance(payload.get("source_data_version"), str)
            or not payload["source_data_version"]
        ):
            raise HistoricalDailyIngestionError("历史日线上游数据版本缺失")
        return payload

    def _normalize_payload(
        self,
        payload: dict[str, Any],
        collected_at: datetime,
        security_id: InstrumentIdentity,
        source_id: str,
        normalized_version_id: str,
    ) -> tuple[bytes, list[IngestedHistoricalDailyBar]]:
        try:
            market_time = datetime.fromisoformat(payload["market_time"])
            records = [
                {
                    "security_id": security_id,
                    "trading_date": bar["trade_date"],
                    "market_time": market_time,
                    "open": bar["open"],
                    "high": bar["high"],
                    "low": bar["low"],
                    "close": bar["close"],
                    "volume": bar["volume"],
                    "currency": payload["currency"],
                    "adjustment_basis": payload["adjustment_basis"],
                    "source_id": source_id,
                    "collected_at": collected_at,
                    "source_data_version": payload["source_data_version"],
                }
                for bar in payload["bars"]
            ]
            normalized = HistoricalDailyBarBatch().normalize(records)
        except (KeyError, TypeError, ValueError, HistoricalDailyBarValidationError) as error:
            raise HistoricalDailyIngestionError(f"历史日线字段或价格无效：{error}") from error
        bars = [
            IngestedHistoricalDailyBar(
                security_id=bar.security_id,
                trade_date=bar.trade_date,
                market_time=bar.market_time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                currency=bar.currency,
                adjustment_basis=bar.adjustment_basis,
                source_id=bar.source_id,
                collected_at=bar.collected_at,
                source_data_version=bar.source_data_version,
            )
            for bar in normalized
        ]
        document = {
            "source_id": source_id,
            "market": security_id.market.value,
            "security_code": security_id.display_code,
            "display_code": security_id.display_code,
            "exchange": security_id.exchange,
            "currency": security_id.currency,
            "market_time": payload["market_time"],
            "collected_at": collected_at.isoformat(),
            "source_data_version": payload["source_data_version"],
            "artifact_version_id": normalized_version_id,
            "bars": [
                {
                    "market": security_id.market.value,
                    "security_code": security_id.display_code,
                    "display_code": security_id.display_code,
                    "exchange": security_id.exchange,
                    "trade_date": bar.trade_date.isoformat(),
                    "market_time": bar.market_time.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "currency": bar.currency,
                    "adjustment_basis": bar.adjustment_basis,
                    "source_id": bar.source_id,
                    "collected_at": bar.collected_at.isoformat(),
                    "source_data_version": bar.source_data_version,
                    "artifact_version_id": normalized_version_id,
                    "freshness": bar.freshness.state,
                }
                for bar in bars
            ],
        }
        return json.dumps(
            document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8"), bars

    def _rollback(self, raw_version_id: str, normalized_version_id: str) -> None:
        self._versioning_service.rollback_versions(
            ("market-data-raw", raw_version_id),
            ("market-data-normalized", normalized_version_id),
        )
