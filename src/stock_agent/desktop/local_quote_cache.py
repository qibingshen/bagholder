"""从不可变本地工件恢复桌面端可展示的最新行情事实。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from stock_agent.adapters.market_data.base import NormalizedQuote
from stock_agent.application.versioning_service import VersioningService


def load_latest_quotes(root: Path) -> tuple[NormalizedQuote, ...]:
    """按证券返回最新采集快照，并忽略未提交或无法验证的工件。"""

    dataset = "market-data-normalized"
    dataset_root = root / "artifacts" / dataset
    if not dataset_root.is_dir():
        return ()

    service = VersioningService(root)
    latest_by_security: dict[str, NormalizedQuote] = {}
    for directory in dataset_root.iterdir():
        if not directory.is_dir() or not service.version_exists(dataset, directory.name):
            continue
        try:
            payload = json.loads(service.read_bytes(dataset, directory.name).decode("utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("quotes"), list):
                records = payload["quotes"]
            else:
                records = payload if isinstance(payload, list) else [payload]
            quotes = tuple(NormalizedQuote.model_validate(record) for record in records)
        except (KeyError, OSError, UnicodeDecodeError, TypeError, ValueError, ValidationError):
            continue
        for quote in quotes:
            key = (
                f"{quote.security_id.market}:"
                f"{quote.security_id.exchange}:{quote.security_id.display_code}"
            )
            previous = latest_by_security.get(key)
            if previous is None or quote.collected_at > previous.collected_at:
                latest_by_security[key] = quote

    return tuple(
        sorted(latest_by_security.values(), key=lambda quote: quote.collected_at, reverse=True)
    )
