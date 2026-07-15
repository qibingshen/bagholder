"""为所有测试提供冻结时间和隔离本地数据目录。"""

from datetime import UTC, datetime
from pathlib import Path

import pytest


@pytest.fixture
def frozen_utc_now() -> datetime:
    """固定当前时间，避免市场时点测试依赖执行机器的真实时钟。"""

    return datetime(2026, 7, 14, 0, 0, tzinfo=UTC)


@pytest.fixture
def local_data_root(tmp_path: Path) -> Path:
    """返回测试专用的数据根目录，防止测试接触用户的本地量化事实。"""

    root = tmp_path / "local-data"
    root.mkdir()
    return root
