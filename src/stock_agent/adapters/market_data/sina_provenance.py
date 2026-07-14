"""将新浪原始响应和规范化行情写入既有本地版本事实链。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from stock_agent.adapters.market_data.sina_adapter import SinaPersistenceProof
from stock_agent.application.versioning_service import VersioningService


class SinaMarketDataFactRecorder:
    """使用版本服务追加保存一批新浪原始响应及其规范化结果。"""

    def __init__(self, versioning_service: VersioningService) -> None:
        """注入项目既有版本服务，避免行情适配器另建存储体系。"""

        self._versioning_service = versioning_service

    def record(self, raw_response: bytes, normalized_content: bytes) -> SinaPersistenceProof:
        """以同一批次公开原始字节和规范化事实载荷。"""

        if not normalized_content:
            raise ValueError("规范化事实载荷不能为空")
        raw_hash = hashlib.sha256(raw_response).hexdigest()
        suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f%z")
        version_prefix = raw_hash[:16]
        raw_version_id = f"sina-{version_prefix}-raw-{suffix}"
        normalized_version_id = f"sina-{version_prefix}-normalized-{suffix}"
        raw, normalized = self._versioning_service.commit_batch(
            batch_id=f"sina-{version_prefix}-{suffix}",
            items=[
                {
                    "dataset": "market-data-raw",
                    "version_id": raw_version_id,
                    "content": raw_response,
                    "source_id": "sina",
                    "expected_hash": raw_hash,
                },
                {
                    "dataset": "market-data-normalized",
                    "version_id": normalized_version_id,
                    "content": normalized_content,
                    "source_id": "sina",
                    "parent_version_id": raw_version_id,
                },
            ],
        )
        return SinaPersistenceProof(
            raw_artifact_version_id=raw.version_id,
            normalized_artifact_version_id=normalized.version_id,
            parent_version_id=normalized.parent_version_id or "",
        )
