"""将新浪原始响应和规范化行情写入既有本地版本事实链。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from stock_agent.adapters.market_data.base import NormalizedQuote
from stock_agent.adapters.market_data.sina_adapter import SinaPersistenceProof
from stock_agent.application.versioning_service import VersioningService


class SinaMarketDataFactRecorder:
    """使用版本服务追加保存一批新浪原始响应及其规范化结果。"""

    def __init__(self, versioning_service: VersioningService) -> None:
        """注入项目既有版本服务，避免行情适配器另建存储体系。"""

        self._versioning_service = versioning_service

    def record(
        self, raw_response: bytes, quotes: Sequence[NormalizedQuote]
    ) -> SinaPersistenceProof:
        """先提交原始字节，再提交引用其版本与哈希的规范化结果。"""

        if not quotes:
            raise ValueError("没有规范化行情时不能建立新浪事实记录")
        first = quotes[0]
        if any(
            quote.source_id != "sina" or quote.data_version != first.data_version
            for quote in quotes
        ):
            raise ValueError("新浪事实记录必须来自同一来源和数据版本")

        raw_hash = hashlib.sha256(raw_response).hexdigest()
        suffix = first.collected_at.astimezone().strftime("%Y%m%dT%H%M%S%f%z")
        version_prefix = raw_hash[:16]
        raw_version_id = f"sina-{version_prefix}-raw-{suffix}"
        raw = self._versioning_service.commit_bytes(
            dataset="market-data-raw",
            version_id=raw_version_id,
            content=raw_response,
            source_id="sina",
            expected_hash=raw_hash,
        )
        normalized_version_id = f"sina-{version_prefix}-normalized-{suffix}"
        normalized_content = json.dumps(
            {
                "source_id": "sina",
                "data_version": first.data_version,
                "raw_artifact_version_id": raw.version_id,
                "raw_content_hash": raw.content_hash,
                "collected_at": first.collected_at.isoformat(),
                "quotes": [quote.model_dump(mode="json") for quote in quotes],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        normalized = self._versioning_service.commit_bytes(
            dataset="market-data-normalized",
            version_id=normalized_version_id,
            content=normalized_content,
            source_id="sina",
            parent_version_id=raw.version_id,
        )
        return SinaPersistenceProof(
            raw_artifact_version_id=raw.version_id,
            raw_content_hash=raw.content_hash,
            normalized_artifact_version_id=normalized.version_id,
            normalized_content_hash=normalized.content_hash,
            parent_version_id=normalized.parent_version_id or "",
        )
