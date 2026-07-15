# T040 审查包

## 提交

6d4c51a feat: add historical daily ingestion worker

## 统计

 .superpowers/sdd/task-040-report.md                |  46 +++++
 .../application/historical_market_data.py          | 136 +++++++++++++
 src/stock_agent/application/versioning_service.py  |  84 ++++++++
 src/stock_agent/workers/market_ingestion.py        | 224 +++++++++++++++++++++
 4 files changed, 490 insertions(+)

## 差异

```diff
diff --git a/.superpowers/sdd/task-040-report.md b/.superpowers/sdd/task-040-report.md
new file mode 100644
index 0000000..43f7d60
--- /dev/null
+++ b/.superpowers/sdd/task-040-report.md
@@ -0,0 +1,46 @@
+# T040 一市场历史日线采集、原子保存与标准化工作者报告
+
+## 实现范围
+
+- 新增 `HistoricalDailyIngestionWorker`：只调用构造时注入的历史日线读取器，不含 HTTP 或其他网络调用。
+- 仅接受 `sina` 与 `CN` 证券身份；保存原始响应与标准化日线，保留来源、市场时间、采集时间、数据版本、内容哈希及父版本关系。
+- 新增 `HistoricalDailyBarBatch` 最小公开接口，任一契约字段缺失、空值或价格区间无效时整批拒绝。
+- 同内容重采集使用新的 UUID 版本标识，保留新的原始工件和对应标准化父链，不覆盖旧版本。
+
+## 红灯证据
+
+命令：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
+```
+
+首次结果：61 项中 37 项失败、24 项通过。目标集成测试的失败原因是
+`ModuleNotFoundError: No module named 'stock_agent.workers.market_ingestion'`，符合 T037 记录的缺失 worker/interface 红灯。
+
+## 绿灯证据
+
+同一命令在实现后结果为 47 项通过、14 项失败。与 T040 有关的 11 个
+`test_single_market_daily_pipeline.py` 用例和 12 个
+`HistoricalDailyBarBatch` 缺字段拒绝用例均通过。剩余 14 项失败属于尚未实现的当前预测新鲜度显式拒绝、跨市场证券身份、公司行为/复权规则，不由本任务改动。
+
+## 回滚策略
+
+工作者在任何读取、解析、标准化或两侧保存失败时，调用同一
+`VersioningService.rollback_versions` 删除本批次已写入的原始与标准化目录、完成标记和 DuckDB 元数据。版本标识在保存前生成，因此即使字节写入、元数据登记或完成标记中途失败，也会清理两侧残留；未对外返回任何部分结果。
+
+## 其他命令结果
+
+```powershell
+py -3.12 -m ruff format --check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py
+py -3.12 -m ruff check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py
+py -3.12 tools/check_chinese_project_text.py
+```
+
+以上检查通过。
+
+全量 `py -3.12 -m pytest -o addopts='' -v` 在收集阶段因既有缺失模块
+`stock_agent.desktop.pages.market_page` 与
+`stock_agent.application.market_service` 报 2 个错误，未进入 T040 测试执行。
+
+全仓 Ruff 同时报告既有测试及工具文件的格式/导入/行长问题；T040 修改文件的格式与检查均通过。
diff --git a/src/stock_agent/application/historical_market_data.py b/src/stock_agent/application/historical_market_data.py
new file mode 100644
index 0000000..811c6f9
--- /dev/null
+++ b/src/stock_agent/application/historical_market_data.py
@@ -0,0 +1,136 @@
+"""历史日线的最小标准化契约。"""
+
+from __future__ import annotations
+
+import math
+from dataclasses import dataclass
+from datetime import date, datetime
+from typing import Any
+
+from stock_agent.application.versioning_service import VersioningService
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+class HistoricalDailyBarValidationError(ValueError):
+    """表示历史日线未满足完整、可追溯的标准化契约。"""
+
+
+@dataclass(frozen=True, slots=True)
+class HistoricalDailyBar:
+    """已标准化的一条历史日线，明确不能作为实时行情使用。"""
+
+    security_id: InstrumentIdentity
+    trade_date: date
+    market_time: datetime
+    open: float
+    high: float
+    low: float
+    close: float
+    volume: float
+    currency: str
+    adjustment_basis: str
+    source_id: str
+    collected_at: datetime
+    data_version: str
+
+
+class HistoricalDailyBarBatch:
+    """对整批历史日线执行先验证、后返回的标准化。"""
+
+    _REQUIRED_FIELDS = {
+        "security_id",
+        "trading_date",
+        "market_time",
+        "open",
+        "high",
+        "low",
+        "close",
+        "volume",
+        "currency",
+        "adjustment_basis",
+        "source_id",
+        "collected_at",
+        "data_version",
+    }
+
+    def __init__(self, versioning_service: VersioningService) -> None:
+        self._versioning_service = versioning_service
+
+    def normalize_and_save(self, records: list[dict[str, Any]]) -> list[HistoricalDailyBar]:
+        """验证完整批次并返回标准化结果；任一记录无效即拒绝整批。"""
+        if not records:
+            raise HistoricalDailyBarValidationError("历史日线批次不能为空")
+        return [self._normalize(record) for record in records]
+
+    def _normalize(self, record: dict[str, Any]) -> HistoricalDailyBar:
+        missing = self._REQUIRED_FIELDS - record.keys()
+        if missing or any(record[field] in (None, "") for field in self._REQUIRED_FIELDS - missing):
+            raise HistoricalDailyBarValidationError("历史日线字段缺失或不完整")
+
+        security_id = record["security_id"]
+        if not isinstance(security_id, InstrumentIdentity) or security_id.market is not Market.CN:
+            raise HistoricalDailyBarValidationError("历史日线证券身份必须属于 CN 市场")
+        if record["currency"] != security_id.currency:
+            raise HistoricalDailyBarValidationError("历史日线币种与证券身份不一致")
+        if not isinstance(record["source_id"], str) or not record["source_id"].strip():
+            raise HistoricalDailyBarValidationError("历史日线来源无效")
+
+        market_time = self._datetime(record["market_time"], "市场时间")
+        collected_at = self._datetime(record["collected_at"], "采集时间")
+        if market_time > collected_at:
+            raise HistoricalDailyBarValidationError("市场时间不能晚于采集时间")
+        try:
+            trade_date = date.fromisoformat(str(record["trading_date"]))
+        except (TypeError, ValueError) as error:
+            raise HistoricalDailyBarValidationError("交易日无效") from error
+
+        open_price = self._number(record["open"], "开盘价")
+        high = self._number(record["high"], "最高价")
+        low = self._number(record["low"], "最低价")
+        close = self._number(record["close"], "收盘价")
+        volume = self._number(record["volume"], "成交量")
+        if low > min(open_price, close) or high < max(open_price, close) or high < low:
+            raise HistoricalDailyBarValidationError("日线价格区间无效")
+        if volume < 0:
+            raise HistoricalDailyBarValidationError("成交量不能为负数")
+        if (
+            not isinstance(record["adjustment_basis"], str)
+            or not record["adjustment_basis"].strip()
+        ):
+            raise HistoricalDailyBarValidationError("复权口径无效")
+        if not isinstance(record["data_version"], str) or not record["data_version"].strip():
+            raise HistoricalDailyBarValidationError("数据版本无效")
+
+        return HistoricalDailyBar(
+            security_id=security_id,
+            trade_date=trade_date,
+            market_time=market_time,
+            open=open_price,
+            high=high,
+            low=low,
+            close=close,
+            volume=volume,
+            currency=record["currency"],
+            adjustment_basis=record["adjustment_basis"],
+            source_id=record["source_id"],
+            collected_at=collected_at,
+            data_version=record["data_version"],
+        )
+
+    @staticmethod
+    def _datetime(value: Any, label: str) -> datetime:
+        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
+            raise HistoricalDailyBarValidationError(f"{label}必须包含时区")
+        return value
+
+    @staticmethod
+    def _number(value: Any, label: str) -> float:
+        if isinstance(value, bool):
+            raise HistoricalDailyBarValidationError(f"{label}无效")
+        try:
+            number = float(value)
+        except (TypeError, ValueError) as error:
+            raise HistoricalDailyBarValidationError(f"{label}无效") from error
+        if not math.isfinite(number):
+            raise HistoricalDailyBarValidationError(f"{label}无效")
+        return number
diff --git a/src/stock_agent/application/versioning_service.py b/src/stock_agent/application/versioning_service.py
new file mode 100644
index 0000000..198ee53
--- /dev/null
+++ b/src/stock_agent/application/versioning_service.py
@@ -0,0 +1,84 @@
+"""通过暂存、校验和原子目录移动保存不可变版本。"""
+
+from __future__ import annotations
+
+import hashlib
+from dataclasses import dataclass
+from pathlib import Path
+
+from stock_agent.adapters.storage.duckdb_store import DuckDbMetadataStore
+from stock_agent.adapters.storage.parquet_store import ParquetArtifactStore
+
+
+class ImmutableVersionError(ValueError):
+    """表示试图覆盖已经提交的量化事实版本。"""
+
+
+@dataclass(frozen=True, slots=True)
+class CommittedVersion:
+    """描述已经校验并可被查询的版本链节点。"""
+
+    dataset: str
+    version_id: str
+    parent_version_id: str | None
+    content_hash: str
+
+
+class VersioningService:
+    """将暂存工件校验后一次性提交，失败时不改变任何已验证版本。"""
+
+    def __init__(self, data_root: Path) -> None:
+        self._root = data_root
+        self._artifacts = ParquetArtifactStore(data_root / "artifacts")
+        self._metadata = DuckDbMetadataStore(data_root / "metadata.duckdb")
+
+    def version_exists(self, dataset: str, version_id: str) -> bool:
+        """判断指定版本是否已经提交。"""
+        return (self._root / "artifacts" / dataset / version_id / "_COMPLETE").is_file()
+
+    def commit_bytes(
+        self,
+        *,
+        dataset: str,
+        version_id: str,
+        content: bytes,
+        source_id: str,
+        parent_version_id: str | None = None,
+        revision_reason: str | None = None,
+        expected_hash: str | None = None,
+    ) -> CommittedVersion:
+        """校验暂存字节后提交新版本，禁止覆盖既有目录。"""
+        if self.version_exists(dataset, version_id):
+            raise ImmutableVersionError("已提交版本不允许静默覆盖")
+        digest = hashlib.sha256(content).hexdigest()
+        if expected_hash is not None and expected_hash != digest:
+            raise ValueError("暂存工件哈希校验失败")
+        artifact = self._artifacts.write_artifact(dataset, version_id, content)
+        self._metadata.register_version(
+            dataset, version_id, artifact.content_hash, parent_version_id
+        )
+        return CommittedVersion(dataset, version_id, parent_version_id, digest)
+
+    def read_bytes(self, dataset: str, version_id: str) -> bytes:
+        """读取指定不可变版本，不隐式改为当前版本。"""
+        return (self._root / "artifacts" / dataset / version_id / "payload.parquet").read_bytes()
+
+    def metadata_for(self, dataset: str, version_id: str) -> dict[str, str | None]:
+        """读取与不可变工件关联的 DuckDB 元数据。"""
+        return self._metadata.get_version(dataset, version_id)
+
+    def rollback_versions(self, *versions: tuple[str, str]) -> None:
+        """删除尚未对外返回的失败批次版本及其元数据。"""
+        for dataset, version_id in versions:
+            self._metadata._connection.execute(
+                "DELETE FROM dataset_versions WHERE dataset = ? AND version_id = ?",
+                [dataset, version_id],
+            )
+            directory = self._root / "artifacts" / dataset / version_id
+            if directory.exists():
+                for path in directory.iterdir():
+                    path.unlink()
+                directory.rmdir()
+                dataset_directory = directory.parent
+                if not any(dataset_directory.iterdir()):
+                    dataset_directory.rmdir()
diff --git a/src/stock_agent/workers/market_ingestion.py b/src/stock_agent/workers/market_ingestion.py
new file mode 100644
index 0000000..f3f8d45
--- /dev/null
+++ b/src/stock_agent/workers/market_ingestion.py
@@ -0,0 +1,224 @@
+"""通过注入读取器采集并原子保存中国市场历史日线。"""
+
+from __future__ import annotations
+
+import json
+from collections.abc import Callable
+from dataclasses import dataclass
+from datetime import datetime
+from hashlib import sha256
+from typing import Any
+from uuid import uuid4
+
+from stock_agent.application.historical_market_data import (
+    HistoricalDailyBar,
+    HistoricalDailyBarBatch,
+    HistoricalDailyBarValidationError,
+)
+from stock_agent.application.versioning_service import VersioningService
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+class HistoricalDailyIngestionError(RuntimeError):
+    """表示历史日线读取、验证或保存失败，且整个批次已回滚。"""
+
+
+@dataclass(frozen=True, slots=True)
+class HistoricalFreshness:
+    """历史数据的新鲜度标识，明确排除实时用途。"""
+
+    state: str = "HISTORICAL"
+
+
+@dataclass(frozen=True, slots=True)
+class IngestedHistoricalDailyBar(HistoricalDailyBar):
+    """附带历史用途标识的标准化日线。"""
+
+    freshness: HistoricalFreshness = HistoricalFreshness()
+
+
+@dataclass(frozen=True, slots=True)
+class HistoricalDailyIngestionResult:
+    """一次可回读历史日线采集的版本链。"""
+
+    bars: list[IngestedHistoricalDailyBar]
+    raw_version_id: str
+    normalized_version_id: str
+
+
+class HistoricalDailyIngestionWorker:
+    """仅协调注入读取器与同一版本服务，不发起任何网络请求。"""
+
+    def __init__(
+        self,
+        *,
+        read_historical_daily: Callable[..., bytes],
+        versioning_service: VersioningService,
+    ) -> None:
+        self._read_historical_daily = read_historical_daily
+        self._versioning_service = versioning_service
+
+    def collect_and_save(
+        self,
+        *,
+        collected_at: datetime,
+        security_id: InstrumentIdentity,
+        source_id: str,
+    ) -> HistoricalDailyIngestionResult:
+        """读取注入响应，验证整批后保存原始和标准化工件。"""
+        raw_version_id = f"raw-{uuid4().hex}"
+        normalized_version_id = f"normalized-{uuid4().hex}"
+        try:
+            self._validate_request(collected_at, security_id, source_id)
+            raw_response = self._read_historical_daily(
+                collected_at=collected_at, security_id=security_id, source_id=source_id
+            )
+            payload = self._parse_payload(raw_response, collected_at, security_id, source_id)
+            normalized_content, bars = self._normalize_payload(
+                payload, collected_at, security_id, source_id, normalized_version_id
+            )
+            self._versioning_service.commit_bytes(
+                dataset="market-data-raw",
+                version_id=raw_version_id,
+                content=raw_response,
+                source_id=source_id,
+                expected_hash=sha256(raw_response).hexdigest(),
+            )
+            self._versioning_service.commit_bytes(
+                dataset="market-data-normalized",
+                version_id=normalized_version_id,
+                content=normalized_content,
+                source_id=source_id,
+                parent_version_id=raw_version_id,
+                expected_hash=sha256(normalized_content).hexdigest(),
+            )
+        except HistoricalDailyIngestionError:
+            self._rollback(raw_version_id, normalized_version_id)
+            raise
+        except Exception as error:
+            self._rollback(raw_version_id, normalized_version_id)
+            raise HistoricalDailyIngestionError(str(error)) from error
+        return HistoricalDailyIngestionResult(bars, raw_version_id, normalized_version_id)
+
+    @staticmethod
+    def _validate_request(
+        collected_at: datetime, security_id: InstrumentIdentity, source_id: str
+    ) -> None:
+        if source_id != "sina":
+            raise HistoricalDailyIngestionError("历史日线来源必须为 sina")
+        if security_id.market is not Market.CN:
+            raise HistoricalDailyIngestionError("历史日线市场必须为 CN")
+        if collected_at.tzinfo is None or collected_at.utcoffset() is None:
+            raise HistoricalDailyIngestionError("采集时间必须包含时区")
+
+    @staticmethod
+    def _parse_payload(
+        raw_response: bytes,
+        collected_at: datetime,
+        security_id: InstrumentIdentity,
+        source_id: str,
+    ) -> dict[str, Any]:
+        if not isinstance(raw_response, bytes):
+            raise HistoricalDailyIngestionError("历史日线读取器必须返回字节")
+        try:
+            payload = json.loads(raw_response)
+        except (UnicodeDecodeError, json.JSONDecodeError) as error:
+            raise HistoricalDailyIngestionError("历史日线原始响应无法解析") from error
+        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), list):
+            raise HistoricalDailyIngestionError("历史日线响应缺少完整 bars 字段")
+        if (
+            payload.get("source_id") != source_id
+            or payload.get("market") != security_id.market.value
+        ):
+            raise HistoricalDailyIngestionError("历史日线来源或市场不一致")
+        if payload.get("collected_at") != collected_at.isoformat():
+            raise HistoricalDailyIngestionError("历史日线采集时间不一致")
+        if not isinstance(payload.get("data_version"), str) or not payload["data_version"]:
+            raise HistoricalDailyIngestionError("历史日线数据版本缺失")
+        return payload
+
+    def _normalize_payload(
+        self,
+        payload: dict[str, Any],
+        collected_at: datetime,
+        security_id: InstrumentIdentity,
+        source_id: str,
+        normalized_version_id: str,
+    ) -> tuple[bytes, list[IngestedHistoricalDailyBar]]:
+        try:
+            market_time = datetime.fromisoformat(payload["market_time"])
+            records = [
+                {
+                    "security_id": security_id,
+                    "trading_date": bar["trade_date"],
+                    "market_time": market_time,
+                    "open": bar["open"],
+                    "high": bar["high"],
+                    "low": bar["low"],
+                    "close": bar["close"],
+                    "volume": bar["volume"],
+                    "currency": security_id.currency,
+                    "adjustment_basis": "none",
+                    "source_id": source_id,
+                    "collected_at": collected_at,
+                    "data_version": normalized_version_id,
+                }
+                for bar in payload["bars"]
+            ]
+            normalized = HistoricalDailyBarBatch(self._versioning_service).normalize_and_save(
+                records
+            )
+        except (KeyError, TypeError, ValueError, HistoricalDailyBarValidationError) as error:
+            raise HistoricalDailyIngestionError(f"历史日线字段或价格无效：{error}") from error
+        bars = [
+            IngestedHistoricalDailyBar(
+                security_id=bar.security_id,
+                trade_date=bar.trade_date,
+                market_time=bar.market_time,
+                open=bar.open,
+                high=bar.high,
+                low=bar.low,
+                close=bar.close,
+                volume=bar.volume,
+                currency=bar.currency,
+                adjustment_basis=bar.adjustment_basis,
+                source_id=bar.source_id,
+                collected_at=bar.collected_at,
+                data_version=bar.data_version,
+            )
+            for bar in normalized
+        ]
+        document = {
+            "source_id": source_id,
+            "market": security_id.market.value,
+            "market_time": payload["market_time"],
+            "collected_at": collected_at.isoformat(),
+            "data_version": normalized_version_id,
+            "bars": [
+                {
+                    "trade_date": bar.trade_date.isoformat(),
+                    "market_time": bar.market_time.isoformat(),
+                    "open": bar.open,
+                    "high": bar.high,
+                    "low": bar.low,
+                    "close": bar.close,
+                    "volume": bar.volume,
+                    "currency": bar.currency,
+                    "adjustment_basis": bar.adjustment_basis,
+                    "source_id": bar.source_id,
+                    "collected_at": bar.collected_at.isoformat(),
+                    "data_version": bar.data_version,
+                    "freshness": bar.freshness.state,
+                }
+                for bar in bars
+            ],
+        }
+        return json.dumps(
+            document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
+        ).encode("utf-8"), bars
+
+    def _rollback(self, raw_version_id: str, normalized_version_id: str) -> None:
+        self._versioning_service.rollback_versions(
+            ("market-data-raw", raw_version_id),
+            ("market-data-normalized", normalized_version_id),
+        )

```

