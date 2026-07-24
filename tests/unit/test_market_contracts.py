from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError


def _bar(day: int = 24):
    from bagholder.contracts.market_data import MarketBar

    return MarketBar(
        date=date(2026, 7, day),
        open=Decimal("10.00"),
        high=Decimal("11.00"),
        low=Decimal("9.00"),
        close=Decimal("10.50"),
        volume=1000,
    )


def test_行情日期必须递增且不能重复() -> None:
    from bagholder.contracts.market_data import MarketSnapshot

    bar = _bar()
    with pytest.raises(ValidationError, match="日期"):
        MarketSnapshot(
            security_key="CN:600519.SH",
            start_date=date(2026, 7, 23),
            end_date=date(2026, 7, 24),
            as_of=date(2026, 7, 24),
            retrieved_at=datetime.now(UTC),
            source="sina HTTP",
            records=[bar, bar],
        )


def test_最高价和最低价必须覆盖开盘收盘价() -> None:
    from bagholder.contracts.market_data import MarketBar

    with pytest.raises(ValidationError, match="OHLC"):
        MarketBar(
            date=date(2026, 7, 24),
            open=Decimal("10.00"),
            high=Decimal("10.20"),
            low=Decimal("9.00"),
            close=Decimal("10.50"),
            volume=1000,
        )


def test_行情结束日期不能晚于分析时点() -> None:
    from bagholder.contracts.market_data import MarketSnapshot

    with pytest.raises(ValidationError, match="分析时点"):
        MarketSnapshot(
            security_key="CN:600519.SH",
            start_date=date(2026, 7, 24),
            end_date=date(2026, 7, 25),
            as_of=date(2026, 7, 24),
            retrieved_at=datetime.now(UTC),
            source="sina HTTP",
            records=[_bar()],
        )

