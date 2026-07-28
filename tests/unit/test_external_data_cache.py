import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

_CACHE_PATH = (
    Path(__file__).parents[2] / "integrations" / "tradingagents" / "external_data_cache.py"
)


def _cache() -> ModuleType:
    spec = importlib.util.spec_from_file_location("external_data_cache", _CACHE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sqlite_cache_returns_fresh_entry(tmp_path: Path) -> None:
    cache = _cache()
    now = datetime(2026, 7, 27, tzinfo=UTC)
    store = cache.SqliteExternalDataCacheStore(tmp_path / "external-data" / "cache.sqlite3")
    entry = cache.CacheEntry.create(
        tool_name="get_fundamentals",
        args=("603986", "2026-07-24"),
        vendor_version="astock-v1",
        payload="fundamentals",
        fetched_at=now,
        expires_at=now + timedelta(hours=24),
    )

    store.put(entry)

    lookup = store.get(entry.cache_key, now + timedelta(minutes=1))

    assert lookup is not None
    assert lookup.payload == "fundamentals"
    assert lookup.stale is False


def test_router_reuses_fresh_data_without_second_upstream_call(tmp_path: Path) -> None:
    cache = _cache()
    calls: list[tuple[object, ...]] = []
    router = cache.CachedVendorRouter(
        upstream=lambda tool_name, *args: calls.append((tool_name, *args)) or "remote-result",
        store=cache.SqliteExternalDataCacheStore(tmp_path / "cache.sqlite3"),
        vendor_version="astock-v1",
    )

    first = router("get_stock_data", "603986", "2026-07-01", "2026-07-24")
    second = router("get_stock_data", "603986", "2026-07-01", "2026-07-24")

    assert first == "remote-result"
    assert second == "remote-result"
    assert calls == [("get_stock_data", "603986", "2026-07-01", "2026-07-24")]


def test_router_returns_stale_data_after_upstream_failure(tmp_path: Path) -> None:
    cache = _cache()
    now = datetime.now(UTC)
    store = cache.SqliteExternalDataCacheStore(tmp_path / "cache.sqlite3")
    store.put(
        cache.CacheEntry.create(
            tool_name="get_profit_forecast",
            args=("603986",),
            vendor_version="astock-v1",
            payload="old-result",
            fetched_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
    )
    router = cache.CachedVendorRouter(
        upstream=lambda tool_name, *args: (_ for _ in ()).throw(TimeoutError("upstream")),
        store=store,
        vendor_version="astock-v1",
    )

    with cache.track_cache_usage() as tracker:
        result = router("get_profit_forecast", "603986")

    assert result == "old-result"
    assert tracker.stale_tool_names == {"get_profit_forecast"}


def test_sqlite_store_close_releases_database_file(tmp_path: Path) -> None:
    cache = _cache()
    database_path = tmp_path / "cache.sqlite3"
    store = cache.SqliteExternalDataCacheStore(database_path)

    store.close()
    database_path.unlink()

    assert not database_path.exists()


def test_sqlite_store_allows_tool_worker_thread_reads(tmp_path: Path) -> None:
    cache = _cache()
    now = datetime.now(UTC)
    store = cache.SqliteExternalDataCacheStore(tmp_path / "cache.sqlite3")
    entry = cache.CacheEntry.create(
        tool_name="get_stock_data",
        args=("603986", "2026-07-01", "2026-07-24"),
        vendor_version="astock-v1",
        payload="market-data",
        fetched_at=now,
        expires_at=now + timedelta(hours=24),
    )
    store.put(entry)

    with ThreadPoolExecutor(max_workers=1) as executor:
        lookup = executor.submit(store.get, entry.cache_key, now).result()

    assert lookup is not None
    assert lookup.payload == "market-data"
