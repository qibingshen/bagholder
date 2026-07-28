"""TradingAgents 外部数据的本地缓存存储契约与 SQLite 实现。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Protocol, cast

_CACHEABLE_TOOLS = frozenset(
    {
        "get_stock_data",
        "get_indicators",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
        "get_profit_forecast",
        "get_industry_comparison",
    }
)
_HOURLY_TOOLS = frozenset({"get_profit_forecast", "get_industry_comparison"})


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def cache_key_for(
    tool_name: str,
    args: tuple[object, ...],
    vendor_version: str,
) -> str:
    """为同一工具、股票、参数和供应商版本构造稳定键。"""

    payload = {
        "args": args,
        "stock_code": str(args[0]) if args else "",
        "tool_name": tool_name,
        "vendor_version": vendor_version,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def ttl_for(tool_name: str) -> timedelta:
    """按数据变化速度返回缓存有效期。"""

    if tool_name in _HOURLY_TOOLS:
        return timedelta(hours=1)
    if tool_name in _CACHEABLE_TOOLS:
        return timedelta(hours=24)
    raise ValueError(f"不支持缓存的工具：{tool_name}")


@dataclass(frozen=True)
class CacheEntry:
    cache_key: str
    tool_name: str
    parameters_json: str
    vendor_version: str
    payload_json: str
    payload_sha256: str
    fetched_at: datetime
    expires_at: datetime

    @classmethod
    def create(
        cls,
        *,
        tool_name: str,
        args: tuple[object, ...],
        vendor_version: str,
        payload: object,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> CacheEntry:
        payload_json = _canonical_json(payload)
        return cls(
            cache_key=cache_key_for(tool_name, args, vendor_version),
            tool_name=tool_name,
            parameters_json=_canonical_json(args),
            vendor_version=vendor_version,
            payload_json=payload_json,
            payload_sha256=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            fetched_at=fetched_at,
            expires_at=expires_at,
        )


@dataclass(frozen=True)
class CacheLookup:
    payload: object
    stale: bool


class ExternalDataCacheStore(Protocol):
    """可替换的缓存存储边界；未来数据库适配器保持同一语义。"""

    def get(self, cache_key: str, now: datetime) -> CacheLookup | None: ...

    def put(self, entry: CacheEntry) -> None: ...

    def delete(self, cache_key: str) -> None: ...

    def close(self) -> None: ...


class SqliteExternalDataCacheStore:
    """以 SQLite 保存可校验外部工具响应。"""

    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS external_data_cache_entries (
                cache_key TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                vendor_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def get(self, cache_key: str, now: datetime) -> CacheLookup | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json, payload_sha256, expires_at
                FROM external_data_cache_entries
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        payload_json = str(row["payload_json"])
        actual_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if actual_sha256 != str(row["payload_sha256"]):
            self.delete(cache_key)
            return None
        try:
            payload = json.loads(payload_json)
            expires_at = datetime.fromisoformat(str(row["expires_at"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            self.delete(cache_key)
            return None
        return CacheLookup(payload=payload, stale=now >= expires_at)

    def put(self, entry: CacheEntry) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO external_data_cache_entries (
                    cache_key, tool_name, parameters_json, vendor_version,
                    payload_json, payload_sha256, fetched_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    tool_name = excluded.tool_name,
                    parameters_json = excluded.parameters_json,
                    vendor_version = excluded.vendor_version,
                    payload_json = excluded.payload_json,
                    payload_sha256 = excluded.payload_sha256,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at
                """,
                (
                    entry.cache_key,
                    entry.tool_name,
                    entry.parameters_json,
                    entry.vendor_version,
                    entry.payload_json,
                    entry.payload_sha256,
                    entry.fetched_at.isoformat(),
                    entry.expires_at.isoformat(),
                ),
            )

    def delete(self, cache_key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM external_data_cache_entries WHERE cache_key = ?",
                (cache_key,),
            )

    def close(self) -> None:
        """释放 SQLite 文件句柄，便于 Windows 清理或替换缓存文件。"""

        with self._lock:
            self._connection.close()


@dataclass
class CacheUsageTracker:
    """记录本次研究使用的过期缓存，供风险结论披露。"""

    stale_tool_names: set[str]

    def mark_stale(self, tool_name: str) -> None:
        self.stale_tool_names.add(tool_name)


_CURRENT_TRACKER: ContextVar[CacheUsageTracker | None] = ContextVar(
    "tradingagents_cache_usage_tracker",
    default=None,
)


@contextmanager
def track_cache_usage() -> Iterator[CacheUsageTracker]:
    """为一次研究建立独立的过期数据使用记录。"""

    tracker = CacheUsageTracker(stale_tool_names=set())
    token = _CURRENT_TRACKER.set(tracker)
    try:
        yield tracker
    finally:
        _CURRENT_TRACKER.reset(token)


class CachedVendorRouter:
    """在公开数据供应商调用前执行统一缓存策略。"""

    def __init__(
        self,
        upstream: Callable[..., str],
        store: ExternalDataCacheStore,
        vendor_version: str,
    ) -> None:
        self._upstream = upstream
        self._store = store
        self._vendor_version = vendor_version

    def __call__(self, tool_name: str, *args: object) -> str:
        if tool_name not in _CACHEABLE_TOOLS:
            return self._upstream(tool_name, *args)
        now = datetime.now(UTC)
        cache_key = cache_key_for(tool_name, args, self._vendor_version)
        lookup = self._store.get(cache_key, now)
        if lookup is not None and not lookup.stale:
            return cast(str, lookup.payload)
        try:
            result = self._upstream(tool_name, *args)
        except Exception:
            if lookup is None:
                raise
            tracker = _CURRENT_TRACKER.get()
            if tracker is not None:
                tracker.mark_stale(tool_name)
            return cast(str, lookup.payload)
        if isinstance(result, str):
            fetched_at = datetime.now(UTC)
            self._store.put(
                CacheEntry.create(
                    tool_name=tool_name,
                    args=args,
                    vendor_version=self._vendor_version,
                    payload=result,
                    fetched_at=fetched_at,
                    expires_at=fetched_at + ttl_for(tool_name),
                )
            )
        return result
