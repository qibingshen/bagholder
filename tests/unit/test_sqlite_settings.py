"""验证 SQLite 仅保存可重建的桌面状态。"""

from pathlib import Path

import pytest


def test_桌面状态可保存但量化事实被拒绝(tmp_path: Path) -> None:
    """行情、预测等事实不得以 SQLite 作为唯一或替代存储。"""

    from stock_agent.adapters.storage.sqlite_settings import (
        DesktopSettingsStore,
        QuantitativeFactForbiddenError,
    )

    store = DesktopSettingsStore(tmp_path / "settings.sqlite")
    store.set("window.geometry", "1200x800")
    assert store.get("window.geometry") == "1200x800"
    with pytest.raises(QuantitativeFactForbiddenError):
        store.set("prediction.latest", '{"up": 0.7}')
