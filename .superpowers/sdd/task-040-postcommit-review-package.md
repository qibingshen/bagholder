# T040 原子性最终复审包（提交后）

## 提交

c1ddd41 fix: harden versioning atomic publication
5349584 fix: recover atomic market data batches
739a1b3 fix: make historical daily batch publication atomic

## 统计

 .superpowers/sdd/task-040-final-review-package.md  | 1381 ++++++++++++++++++++
 .superpowers/sdd/task-040-fix-report.md            |   55 +
 .superpowers/sdd/task-040-fix2-report.md           |   41 +
 .superpowers/sdd/task-040-fix3-report.md           |   42 +
 .../adapters/market_data/sina_provenance.py        |   33 +-
 src/stock_agent/adapters/storage/duckdb_store.py   |   81 ++
 src/stock_agent/adapters/storage/parquet_store.py  |   37 +
 .../application/historical_market_data.py          |   21 +-
 src/stock_agent/application/versioning_service.py  |  241 +++-
 src/stock_agent/workers/market_ingestion.py        |   79 +-
 tests/failure/test_market_data_failures.py         |   12 +-
 .../test_sina_market_data_provenance.py            |   25 +
 .../test_single_market_daily_pipeline.py           |  104 +-
 tests/integration/test_versioning_atomic_commit.py |  206 +++
 14 files changed, 2252 insertions(+), 106 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/task-040-final-review-package.md b/.superpowers/sdd/task-040-final-review-package.md
new file mode 100644
index 0000000..240ed29
--- /dev/null
+++ b/.superpowers/sdd/task-040-final-review-package.md
@@ -0,0 +1,1381 @@
+# T040 最终原子性复审包
+
+## 提交
+
+5349584 fix: recover atomic market data batches
+739a1b3 fix: make historical daily batch publication atomic
+
+## 统计
+
+ .superpowers/sdd/task-040-fix-report.md            |  55 ++++++
+ .superpowers/sdd/task-040-fix2-report.md           |  41 +++++
+ .../adapters/market_data/sina_provenance.py        |  33 ++--
+ src/stock_agent/adapters/storage/duckdb_store.py   |  71 ++++++++
+ src/stock_agent/adapters/storage/parquet_store.py  |  37 ++++
+ .../application/historical_market_data.py          |  21 ++-
+ src/stock_agent/application/versioning_service.py  | 198 ++++++++++++++++++---
+ src/stock_agent/workers/market_ingestion.py        |  71 ++++----
+ tests/failure/test_market_data_failures.py         |  12 +-
+ .../test_sina_market_data_provenance.py            |  25 +++
+ .../test_single_market_daily_pipeline.py           |  98 +++++++---
+ tests/integration/test_versioning_atomic_commit.py | 101 +++++++++++
+ 12 files changed, 658 insertions(+), 105 deletions(-)
+
+## 差异
+
+```diff
+diff --git a/.superpowers/sdd/task-040-fix-report.md b/.superpowers/sdd/task-040-fix-report.md
+new file mode 100644
+index 0000000..3bd3826
+--- /dev/null
++++ b/.superpowers/sdd/task-040-fix-report.md
+@@ -0,0 +1,55 @@
++# T040 独立审查问题修复报告
++
++## 修复结果
++
++- `VersioningService.commit_batch()` 为原始和规范化工件建立同一批次日志；两侧先写入无 `_COMPLETE` 的暂存工件并登记元数据，最后只在 `.batches/<batch_id>/_COMPLETE` 写入单一完成标记。
++- `version_exists()`、`read_bytes()` 与 `metadata_for()` 仅将单版本完成工件或含单一批次完成标记的批次成员视为可见。批次中断、完成标记失败或补偿失败均不会让任一侧独立可查询。
++- 服务初始化会扫描未完成批次日志，幂等删除工件目录和 DuckDB 元数据，作为进程中断或补偿失败后的恢复策略。
++- 标准化接口改为准确的 `HistoricalDailyBarBatch.normalize()`，仅执行全批校验和标准化；持久化只能由受控的 `HistoricalDailyIngestionWorker` 完成。
++- 规范化产物保留 `source_data_version`、`adjustment_basis` 和本地 `artifact_version_id`，不再使用本地 UUID 覆盖上游来源版本。
++- 载荷必须显式携带并匹配 `security_code`、`exchange`、`currency`、`market`；任一不匹配会整批拒绝且不留可见工件或元数据。
++
++## TDD 红灯与绿灯
++
++先新增并运行以下回归测试，红灯分别证明旧实现缺少来源版本保留、未核验代码/交易所/币种，以及存在两侧独立完成标记：
++
++- 批次唯一完成标记失败时两侧均不可查询，并在下次启动恢复。
++- 上游证券代码、交易所、币种、市场任一不匹配时整批拒绝。
++- 规范化工件同时保存上游版本、复权口径和本地产物版本。
++
++实现后，以下相关组合测试通过：
++
++```powershell
++py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py -v
++```
++
++结果：`27 passed`。
++
++按任务指定组合运行：
++
++```powershell
++py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -q
++```
++
++结果：`52 passed, 14 failed`。14 项均为本任务范围外的既有缺口：当前预测新鲜度拒绝、跨市场证券身份校验、代码歧义解析、公司行动与复权规则；未涉及本次批次提交路径。
++
++## 质量检查
++
++```powershell
++py -3.12 -m ruff format --check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py src/stock_agent/adapters/storage/parquet_store.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py
++py -3.12 -m ruff check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py src/stock_agent/adapters/storage/parquet_store.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py
++py -3.12 tools/check_chinese_project_text.py
++```
++
++三项检查均通过。
++
++全量命令 `py -3.12 -m pytest -o addopts='' -q` 在收集阶段被既有缺失模块阻断：
++
++- `stock_agent.desktop.pages.market_page`
++- `stock_agent.application.market_service`
++
++因此未能进入完整测试执行；该阻断与本次修改无关。
++
++## 风险与恢复边界
++
++批次完成标记写入前，即使原始或规范化目录、元数据已经存在，也不会被本服务的查询接口视为可见版本；启动恢复会清除未完成批次。单一完成标记写入后两侧同时公开。当前实现依赖所有调用方通过 `VersioningService` 查询，不应绕过服务直接枚举 `artifacts` 目录并将无完成标记目录当作有效版本。
+diff --git a/.superpowers/sdd/task-040-fix2-report.md b/.superpowers/sdd/task-040-fix2-report.md
+new file mode 100644
+index 0000000..5d66503
+--- /dev/null
++++ b/.superpowers/sdd/task-040-fix2-report.md
+@@ -0,0 +1,41 @@
++# T040 原子发布第二轮修复报告
++
++## 修复结果
++
++- `SinaMarketDataFactRecorder` 已改为一次调用 `VersioningService.commit_batch()` 发布原始响应与规范化事实；任一工件写入失败时，批次回滚原始工件、规范化工件和两者元数据，不产生单侧 `_COMPLETE`。
++- 批次 journal 先写入同目录临时文件，再以替换操作发布 `manifest.json`，避免直接覆盖留下截断内容。
++- DuckDB 增加批次成员恢复索引。启动恢复将 JSON 截断、缺少 `entries` 或条目结构无效的 journal 都视为未完成批次，以恢复索引和可解析日志的并集清理工件与元数据，不让 JSON 解析异常阻断初始化。
++- 未改变历史日线 worker 的 `commit_batch()` 使用方式、来源时点字段或版本语义；测试全程没有真实网络或交易。
++
++## TDD 证据
++
++- 先新增真实 Sina 记录器的规范化工件写入失败回归：旧实现失败后仍保留 `market-data-raw`。
++- 先新增损坏 journal 恢复回归：旧实现缺少批次恢复索引；补充 `{}` 合法但结构损坏场景后，旧实现因 `KeyError: 'entries'` 阻断初始化。
++- 最小实现后，两类回归均转绿。
++
++## 验证结果
++
++```powershell
++py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -q
++```
++
++结果：`65 passed, 14 failed`。14 项均为既有且不属于本次批次发布路径的市场规则、当前预测新鲜度和公司行动缺口。
++
++```powershell
++py -3.12 -m pytest -o addopts='' -q
++```
++
++全量在收集阶段被既有缺失模块阻断：`stock_agent.desktop.pages.market_page` 与 `stock_agent.application.market_service`。
++
++```powershell
++py -3.12 -m ruff format --check src/stock_agent/adapters/market_data/sina_provenance.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/application/versioning_service.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_versioning_atomic_commit.py
++py -3.12 -m ruff check src/stock_agent/adapters/market_data/sina_provenance.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/application/versioning_service.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_versioning_atomic_commit.py
++py -3.12 tools/check_chinese_project_text.py
++```
++
++三项检查通过。
++
++## 风险边界
++
++- 批次完成标记写入前，版本服务不会把任一成员视为可见；启动恢复会清理未完成或日志无效的批次。
++- 损坏日志恢复依赖批次成员恢复索引；该索引在每个成员的元数据登记时写入，覆盖已登记的双侧残留。
+diff --git a/src/stock_agent/adapters/market_data/sina_provenance.py b/src/stock_agent/adapters/market_data/sina_provenance.py
+index 73ead60..17ea4be 100644
+--- a/src/stock_agent/adapters/market_data/sina_provenance.py
++++ b/src/stock_agent/adapters/market_data/sina_provenance.py
+@@ -11,38 +11,43 @@ from stock_agent.application.versioning_service import VersioningService
+ 
+ class SinaMarketDataFactRecorder:
+     """使用版本服务追加保存一批新浪原始响应及其规范化结果。"""
+ 
+     def __init__(self, versioning_service: VersioningService) -> None:
+         """注入项目既有版本服务，避免行情适配器另建存储体系。"""
+ 
+         self._versioning_service = versioning_service
+ 
+     def record(self, raw_response: bytes, normalized_content: bytes) -> SinaPersistenceProof:
+-        """先提交原始字节，再原样提交适配器提供的规范化事实载荷。"""
++        """以同一批次公开原始字节和规范化事实载荷。"""
+ 
+         if not normalized_content:
+             raise ValueError("规范化事实载荷不能为空")
+         raw_hash = hashlib.sha256(raw_response).hexdigest()
+         suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f%z")
+         version_prefix = raw_hash[:16]
+         raw_version_id = f"sina-{version_prefix}-raw-{suffix}"
+-        raw = self._versioning_service.commit_bytes(
+-            dataset="market-data-raw",
+-            version_id=raw_version_id,
+-            content=raw_response,
+-            source_id="sina",
+-            expected_hash=raw_hash,
+-        )
+         normalized_version_id = f"sina-{version_prefix}-normalized-{suffix}"
+-        normalized = self._versioning_service.commit_bytes(
+-            dataset="market-data-normalized",
+-            version_id=normalized_version_id,
+-            content=normalized_content,
+-            source_id="sina",
+-            parent_version_id=raw.version_id,
++        raw, normalized = self._versioning_service.commit_batch(
++            batch_id=f"sina-{version_prefix}-{suffix}",
++            items=[
++                {
++                    "dataset": "market-data-raw",
++                    "version_id": raw_version_id,
++                    "content": raw_response,
++                    "source_id": "sina",
++                    "expected_hash": raw_hash,
++                },
++                {
++                    "dataset": "market-data-normalized",
++                    "version_id": normalized_version_id,
++                    "content": normalized_content,
++                    "source_id": "sina",
++                    "parent_version_id": raw_version_id,
++                },
++            ],
+         )
+         return SinaPersistenceProof(
+             raw_artifact_version_id=raw.version_id,
+             normalized_artifact_version_id=normalized.version_id,
+             parent_version_id=normalized.parent_version_id or "",
+         )
+diff --git a/src/stock_agent/adapters/storage/duckdb_store.py b/src/stock_agent/adapters/storage/duckdb_store.py
+new file mode 100644
+index 0000000..61f1ba2
+--- /dev/null
++++ b/src/stock_agent/adapters/storage/duckdb_store.py
+@@ -0,0 +1,71 @@
++"""使用 DuckDB 追加登记已提交的数据版本。"""
++
++from pathlib import Path
++
++import duckdb
++
++
++class DuckDbMetadataStore:
++    """将版本元数据置于事务中，避免工件可见但版本链缺失。"""
++
++    def __init__(self, database_path: Path) -> None:
++        self._connection = duckdb.connect(str(database_path))
++        self._connection.execute(
++            "CREATE TABLE IF NOT EXISTS dataset_versions ("
++            "dataset VARCHAR, version_id VARCHAR, content_hash VARCHAR, "
++            "parent_version_id VARCHAR, PRIMARY KEY(dataset, version_id))"
++        )
++        self._connection.execute(
++            "CREATE TABLE IF NOT EXISTS batch_versions ("
++            "batch_id VARCHAR, dataset VARCHAR, version_id VARCHAR, "
++            "PRIMARY KEY(batch_id, dataset, version_id))"
++        )
++
++    def register_version(
++        self, dataset: str, version_id: str, content_hash: str, parent_version_id: str | None
++    ) -> None:
++        """原子登记一个不可覆盖的数据版本。"""
++        self._connection.execute(
++            "INSERT INTO dataset_versions VALUES (?, ?, ?, ?)",
++            [dataset, version_id, content_hash, parent_version_id],
++        )
++
++    def register_batch_version(
++        self,
++        batch_id: str,
++        dataset: str,
++        version_id: str,
++        content_hash: str,
++        parent_version_id: str | None,
++    ) -> None:
++        """登记未完成批次成员，供损坏日志的启动恢复定位残留。"""
++        self.register_version(dataset, version_id, content_hash, parent_version_id)
++        self._connection.execute(
++            "INSERT INTO batch_versions VALUES (?, ?, ?)",
++            [batch_id, dataset, version_id],
++        )
++
++    def batch_versions(self, batch_id: str) -> list[tuple[str, str]]:
++        """返回批次已登记成员，不依赖磁盘日志的可解析性。"""
++        return [
++            (row[0], row[1])
++            for row in self._connection.execute(
++                "SELECT dataset, version_id FROM batch_versions WHERE batch_id = ?",
++                [batch_id],
++            ).fetchall()
++        ]
++
++    def delete_batch_versions(self, batch_id: str) -> None:
++        """删除已回滚批次的恢复索引。"""
++        self._connection.execute("DELETE FROM batch_versions WHERE batch_id = ?", [batch_id])
++
++    def get_version(self, dataset: str, version_id: str) -> dict[str, str | None]:
++        """读取指定版本，不隐式返回最新版本。"""
++        row = self._connection.execute(
++            "SELECT content_hash, parent_version_id FROM dataset_versions "
++            "WHERE dataset = ? AND version_id = ?",
++            [dataset, version_id],
++        ).fetchone()
++        if row is None:
++            raise KeyError(version_id)
++        return {"content_hash": row[0], "parent_version_id": row[1]}
+diff --git a/src/stock_agent/adapters/storage/parquet_store.py b/src/stock_agent/adapters/storage/parquet_store.py
+new file mode 100644
+index 0000000..8d00935
+--- /dev/null
++++ b/src/stock_agent/adapters/storage/parquet_store.py
+@@ -0,0 +1,37 @@
++"""保存带哈希、清单和完成标记的不可变工件目录。"""
++
++import hashlib
++import json
++from dataclasses import dataclass
++from pathlib import Path
++
++
++@dataclass(frozen=True, slots=True)
++class StoredArtifact:
++    """描述已完成的不可变工件。"""
++
++    content_hash: str
++    complete_marker: Path
++
++
++class ParquetArtifactStore:
++    """为后续 Parquet 行情和特征文件提供版本目录及完成证据。"""
++
++    def __init__(self, root: Path) -> None:
++        self._root = root
++
++    def write_artifact(
++        self, dataset: str, version_id: str, content: bytes, *, complete: bool = True
++    ) -> StoredArtifact:
++        """写入工件；批次提交时由统一完成标记决定可见性。"""
++        directory = self._root / dataset / version_id
++        directory.mkdir(parents=True, exist_ok=False)
++        digest = hashlib.sha256(content).hexdigest()
++        (directory / "payload.parquet").write_bytes(content)
++        (directory / "manifest.json").write_text(
++            json.dumps({"content_hash": digest}), encoding="utf-8"
++        )
++        marker = directory / "_COMPLETE"
++        if complete:
++            marker.touch()
++        return StoredArtifact(digest, marker)
+diff --git a/src/stock_agent/application/historical_market_data.py b/src/stock_agent/application/historical_market_data.py
+index 811c6f9..5f0fda8 100644
+--- a/src/stock_agent/application/historical_market_data.py
++++ b/src/stock_agent/application/historical_market_data.py
+@@ -1,20 +1,19 @@
+ """历史日线的最小标准化契约。"""
+ 
+ from __future__ import annotations
+ 
+ import math
+ from dataclasses import dataclass
+ from datetime import date, datetime
+ from typing import Any
+ 
+-from stock_agent.application.versioning_service import VersioningService
+ from stock_agent.domain.market import InstrumentIdentity, Market
+ 
+ 
+ class HistoricalDailyBarValidationError(ValueError):
+     """表示历史日线未满足完整、可追溯的标准化契约。"""
+ 
+ 
+ @dataclass(frozen=True, slots=True)
+ class HistoricalDailyBar:
+     """已标准化的一条历史日线，明确不能作为实时行情使用。"""
+@@ -24,47 +23,44 @@ class HistoricalDailyBar:
+     market_time: datetime
+     open: float
+     high: float
+     low: float
+     close: float
+     volume: float
+     currency: str
+     adjustment_basis: str
+     source_id: str
+     collected_at: datetime
+-    data_version: str
++    source_data_version: str
+ 
+ 
+ class HistoricalDailyBarBatch:
+     """对整批历史日线执行先验证、后返回的标准化。"""
+ 
+     _REQUIRED_FIELDS = {
+         "security_id",
+         "trading_date",
+         "market_time",
+         "open",
+         "high",
+         "low",
+         "close",
+         "volume",
+         "currency",
+         "adjustment_basis",
+         "source_id",
+         "collected_at",
+-        "data_version",
++        "source_data_version",
+     }
+ 
+-    def __init__(self, versioning_service: VersioningService) -> None:
+-        self._versioning_service = versioning_service
+-
+-    def normalize_and_save(self, records: list[dict[str, Any]]) -> list[HistoricalDailyBar]:
+-        """验证完整批次并返回标准化结果；任一记录无效即拒绝整批。"""
++    def normalize(self, records: list[dict[str, Any]]) -> list[HistoricalDailyBar]:
++        """验证完整批次并返回标准化结果，不执行持久化。"""
+         if not records:
+             raise HistoricalDailyBarValidationError("历史日线批次不能为空")
+         return [self._normalize(record) for record in records]
+ 
+     def _normalize(self, record: dict[str, Any]) -> HistoricalDailyBar:
+         missing = self._REQUIRED_FIELDS - record.keys()
+         if missing or any(record[field] in (None, "") for field in self._REQUIRED_FIELDS - missing):
+             raise HistoricalDailyBarValidationError("历史日线字段缺失或不完整")
+ 
+         security_id = record["security_id"]
+@@ -91,37 +87,40 @@ class HistoricalDailyBarBatch:
+         volume = self._number(record["volume"], "成交量")
+         if low > min(open_price, close) or high < max(open_price, close) or high < low:
+             raise HistoricalDailyBarValidationError("日线价格区间无效")
+         if volume < 0:
+             raise HistoricalDailyBarValidationError("成交量不能为负数")
+         if (
+             not isinstance(record["adjustment_basis"], str)
+             or not record["adjustment_basis"].strip()
+         ):
+             raise HistoricalDailyBarValidationError("复权口径无效")
+-        if not isinstance(record["data_version"], str) or not record["data_version"].strip():
+-            raise HistoricalDailyBarValidationError("数据版本无效")
++        if (
++            not isinstance(record["source_data_version"], str)
++            or not record["source_data_version"].strip()
++        ):
++            raise HistoricalDailyBarValidationError("上游数据版本无效")
+ 
+         return HistoricalDailyBar(
+             security_id=security_id,
+             trade_date=trade_date,
+             market_time=market_time,
+             open=open_price,
+             high=high,
+             low=low,
+             close=close,
+             volume=volume,
+             currency=record["currency"],
+             adjustment_basis=record["adjustment_basis"],
+             source_id=record["source_id"],
+             collected_at=collected_at,
+-            data_version=record["data_version"],
++            source_data_version=record["source_data_version"],
+         )
+ 
+     @staticmethod
+     def _datetime(value: Any, label: str) -> datetime:
+         if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
+             raise HistoricalDailyBarValidationError(f"{label}必须包含时区")
+         return value
+ 
+     @staticmethod
+     def _number(value: Any, label: str) -> float:
+diff --git a/src/stock_agent/application/versioning_service.py b/src/stock_agent/application/versioning_service.py
+index 198ee53..835933a 100644
+--- a/src/stock_agent/application/versioning_service.py
++++ b/src/stock_agent/application/versioning_service.py
+@@ -1,84 +1,242 @@
+-"""通过暂存、校验和原子目录移动保存不可变版本。"""
++"""通过单一批次完成标记发布不可变版本，并在启动时恢复未完成批次。"""
+ 
+ from __future__ import annotations
+ 
+ import hashlib
++import json
++import shutil
++import uuid
+ from dataclasses import dataclass
+ from pathlib import Path
++from typing import Any
+ 
+ from stock_agent.adapters.storage.duckdb_store import DuckDbMetadataStore
+ from stock_agent.adapters.storage.parquet_store import ParquetArtifactStore
+ 
+ 
+ class ImmutableVersionError(ValueError):
+     """表示试图覆盖已经提交的量化事实版本。"""
+ 
+ 
+ @dataclass(frozen=True, slots=True)
+ class CommittedVersion:
+     """描述已经校验并可被查询的版本链节点。"""
+ 
+     dataset: str
+     version_id: str
+     parent_version_id: str | None
+     content_hash: str
+ 
+ 
+ class VersioningService:
+-    """将暂存工件校验后一次性提交，失败时不改变任何已验证版本。"""
++    """以批次日志和唯一完成标记保证多工件不会独立对外可见。"""
+ 
+     def __init__(self, data_root: Path) -> None:
+         self._root = data_root
+         self._artifacts = ParquetArtifactStore(data_root / "artifacts")
+         self._metadata = DuckDbMetadataStore(data_root / "metadata.duckdb")
++        self._batches_root = data_root / ".batches"
++        self._recover_incomplete_batches()
+ 
+     def version_exists(self, dataset: str, version_id: str) -> bool:
+-        """判断指定版本是否已经提交。"""
+-        return (self._root / "artifacts" / dataset / version_id / "_COMPLETE").is_file()
++        """只把单版本完成标记或已完成批次中的版本视为可查询。"""
++        if (self._root / "artifacts" / dataset / version_id / "_COMPLETE").is_file():
++            return True
++        return self._completed_batch_contains(dataset, version_id)
+ 
+     def commit_bytes(
+         self,
+         *,
+         dataset: str,
+         version_id: str,
+         content: bytes,
+         source_id: str,
+         parent_version_id: str | None = None,
+         revision_reason: str | None = None,
+         expected_hash: str | None = None,
+     ) -> CommittedVersion:
+-        """校验暂存字节后提交新版本，禁止覆盖既有目录。"""
++        """提交单个既有工件；多工件必须改用 ``commit_batch``。"""
+         if self.version_exists(dataset, version_id):
+             raise ImmutableVersionError("已提交版本不允许静默覆盖")
+-        digest = hashlib.sha256(content).hexdigest()
+-        if expected_hash is not None and expected_hash != digest:
+-            raise ValueError("暂存工件哈希校验失败")
++        digest = self._validate_hash(content, expected_hash)
+         artifact = self._artifacts.write_artifact(dataset, version_id, content)
+-        self._metadata.register_version(
+-            dataset, version_id, artifact.content_hash, parent_version_id
+-        )
++        try:
++            self._metadata.register_version(
++                dataset, version_id, artifact.content_hash, parent_version_id
++            )
++        except Exception:
++            self.rollback_versions((dataset, version_id))
++            raise
+         return CommittedVersion(dataset, version_id, parent_version_id, digest)
+ 
++    def commit_batch(self, *, batch_id: str, items: list[dict[str, Any]]) -> list[CommittedVersion]:
++        """暂存整批工件，最后仅写一个批次完成标记以原子公开。"""
++        if not batch_id or not items:
++            raise ValueError("批次标识和工件不能为空")
++        batch_directory = self._batch_directory(batch_id)
++        journal = batch_directory / "manifest.json"
++        if journal.exists() or (batch_directory / "_COMPLETE").exists():
++            raise ImmutableVersionError("批次标识不允许重复使用")
++        entries = []
++        for item in items:
++            dataset, version_id, content = item["dataset"], item["version_id"], item["content"]
++            if (
++                self.version_exists(dataset, version_id)
++                or (self._root / "artifacts" / dataset / version_id).exists()
++            ):
++                raise ImmutableVersionError("批次包含已存在版本")
++            entries.append(
++                {
++                    "dataset": dataset,
++                    "version_id": version_id,
++                    "parent_version_id": item.get("parent_version_id"),
++                    "content_hash": self._validate_hash(content, item.get("expected_hash")),
++                }
++            )
++        batch_directory.mkdir(parents=True, exist_ok=False)
++        self._write_journal_atomically(journal, entries)
++        committed: list[CommittedVersion] = []
++        try:
++            for item, entry in zip(items, entries, strict=True):
++                artifact = self._artifacts.write_artifact(
++                    entry["dataset"], entry["version_id"], item["content"], complete=False
++                )
++                self._metadata.register_batch_version(
++                    batch_id,
++                    entry["dataset"],
++                    entry["version_id"],
++                    artifact.content_hash,
++                    entry["parent_version_id"],
++                )
++                committed.append(
++                    CommittedVersion(
++                        entry["dataset"],
++                        entry["version_id"],
++                        entry["parent_version_id"],
++                        entry["content_hash"],
++                    )
++                )
++            (batch_directory / "_COMPLETE").touch()
++        except Exception:
++            try:
++                self.rollback_batch(batch_id)
++            except Exception:
++                # 日志保留给下一次服务启动恢复；不会形成可查询版本。
++                pass
++            raise
++        return committed
++
+     def read_bytes(self, dataset: str, version_id: str) -> bytes:
+-        """读取指定不可变版本，不隐式改为当前版本。"""
++        """只读取已经公开的版本。"""
++        if not self.version_exists(dataset, version_id):
++            raise KeyError(version_id)
+         return (self._root / "artifacts" / dataset / version_id / "payload.parquet").read_bytes()
+ 
+     def metadata_for(self, dataset: str, version_id: str) -> dict[str, str | None]:
+-        """读取与不可变工件关联的 DuckDB 元数据。"""
++        """只读取已经公开版本的元数据。"""
++        if not self.version_exists(dataset, version_id):
++            raise KeyError(version_id)
+         return self._metadata.get_version(dataset, version_id)
+ 
++    def rollback_batch(self, batch_id: str) -> None:
++        """删除未完成批次的工件和元数据；失败日志留待下次启动继续恢复。"""
++        batch_directory = self._batch_directory(batch_id)
++        versions = set(self._metadata.batch_versions(batch_id))
++        versions.update(self._journal_versions(batch_directory / "manifest.json"))
++        if versions:
++            self.rollback_versions(*versions)
++        self._metadata.delete_batch_versions(batch_id)
++        shutil.rmtree(batch_directory, ignore_errors=False)
++        if self._batches_root.exists() and not any(self._batches_root.iterdir()):
++            self._batches_root.rmdir()
++
+     def rollback_versions(self, *versions: tuple[str, str]) -> None:
+-        """删除尚未对外返回的失败批次版本及其元数据。"""
++        """删除尚未公开的失败版本及其元数据。"""
+         for dataset, version_id in versions:
+             self._metadata._connection.execute(
+                 "DELETE FROM dataset_versions WHERE dataset = ? AND version_id = ?",
+                 [dataset, version_id],
+             )
+             directory = self._root / "artifacts" / dataset / version_id
+             if directory.exists():
+-                for path in directory.iterdir():
+-                    path.unlink()
+-                directory.rmdir()
+-                dataset_directory = directory.parent
+-                if not any(dataset_directory.iterdir()):
+-                    dataset_directory.rmdir()
++                shutil.rmtree(directory)
++            dataset_directory = directory.parent
++            if dataset_directory.exists() and not any(dataset_directory.iterdir()):
++                dataset_directory.rmdir()
++
++    def _recover_incomplete_batches(self) -> None:
++        """启动时幂等清理未写唯一完成标记的中断批次。"""
++        if not self._batches_root.exists():
++            return
++        for directory in list(self._batches_root.iterdir()):
++            if directory.is_dir() and (
++                not (directory / "_COMPLETE").is_file()
++                or not self._journal_is_valid(directory / "manifest.json")
++            ):
++                self.rollback_batch(directory.name)
++
++    def _completed_batch_contains(self, dataset: str, version_id: str) -> bool:
++        if not self._batches_root.exists():
++            return False
++        for directory in self._batches_root.iterdir():
++            manifest = directory / "manifest.json"
++            if not (directory / "_COMPLETE").is_file() or not manifest.is_file():
++                continue
++            if not self._journal_is_valid(manifest):
++                continue
++            entries = self._journal_entries(manifest)
++            if any(
++                entry["dataset"] == dataset and entry["version_id"] == version_id
++                for entry in entries
++            ):
++                return True
++        return False
++
++    def _batch_directory(self, batch_id: str) -> Path:
++        return self._batches_root / batch_id
++
++    @staticmethod
++    def _write_journal_atomically(journal: Path, entries: list[dict[str, Any]]) -> None:
++        temporary = journal.with_name(f".{journal.name}.{uuid.uuid4().hex}.tmp")
++        try:
++            temporary.write_text(json.dumps({"entries": entries}, sort_keys=True), encoding="utf-8")
++            temporary.replace(journal)
++        finally:
++            if temporary.exists():
++                temporary.unlink()
++
++    @classmethod
++    def _journal_is_valid(cls, manifest: Path) -> bool:
++        try:
++            cls._journal_entries(manifest)
++        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
++            return False
++        return True
++
++    @staticmethod
++    def _journal_entries(manifest: Path) -> list[dict[str, Any]]:
++        entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
++        if not isinstance(entries, list) or any(
++            not isinstance(entry, dict)
++            or not isinstance(entry.get("dataset"), str)
++            or not isinstance(entry.get("version_id"), str)
++            for entry in entries
++        ):
++            raise ValueError("批次日志条目无效")
++        return entries
++
++    @classmethod
++    def _journal_versions(cls, manifest: Path) -> set[tuple[str, str]]:
++        try:
++            return {
++                (entry["dataset"], entry["version_id"]) for entry in cls._journal_entries(manifest)
++            }
++        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
++            return set()
++
++    @staticmethod
++    def _validate_hash(content: bytes, expected_hash: str | None) -> str:
++        digest = hashlib.sha256(content).hexdigest()
++        if expected_hash is not None and expected_hash != digest:
++            raise ValueError("暂存工件哈希校验失败")
++        return digest
+diff --git a/src/stock_agent/workers/market_ingestion.py b/src/stock_agent/workers/market_ingestion.py
+index f3f8d45..89aa74f 100644
+--- a/src/stock_agent/workers/market_ingestion.py
++++ b/src/stock_agent/workers/market_ingestion.py
+@@ -1,19 +1,18 @@
+ """通过注入读取器采集并原子保存中国市场历史日线。"""
+ 
+ from __future__ import annotations
+ 
+ import json
+ from collections.abc import Callable
+ from dataclasses import dataclass
+ from datetime import datetime
+-from hashlib import sha256
+ from typing import Any
+ from uuid import uuid4
+ 
+ from stock_agent.application.historical_market_data import (
+     HistoricalDailyBar,
+     HistoricalDailyBarBatch,
+     HistoricalDailyBarValidationError,
+ )
+ from stock_agent.application.versioning_service import VersioningService
+ from stock_agent.domain.market import InstrumentIdentity, Market
+@@ -70,34 +69,35 @@ class HistoricalDailyIngestionWorker:
+         normalized_version_id = f"normalized-{uuid4().hex}"
+         try:
+             self._validate_request(collected_at, security_id, source_id)
+             raw_response = self._read_historical_daily(
+                 collected_at=collected_at, security_id=security_id, source_id=source_id
+             )
+             payload = self._parse_payload(raw_response, collected_at, security_id, source_id)
+             normalized_content, bars = self._normalize_payload(
+                 payload, collected_at, security_id, source_id, normalized_version_id
+             )
+-            self._versioning_service.commit_bytes(
+-                dataset="market-data-raw",
+-                version_id=raw_version_id,
+-                content=raw_response,
+-                source_id=source_id,
+-                expected_hash=sha256(raw_response).hexdigest(),
+-            )
+-            self._versioning_service.commit_bytes(
+-                dataset="market-data-normalized",
+-                version_id=normalized_version_id,
+-                content=normalized_content,
+-                source_id=source_id,
+-                parent_version_id=raw_version_id,
+-                expected_hash=sha256(normalized_content).hexdigest(),
++            self._versioning_service.commit_batch(
++                batch_id=f"historical-daily-{uuid4().hex}",
++                items=[
++                    {
++                        "dataset": "market-data-raw",
++                        "version_id": raw_version_id,
++                        "content": raw_response,
++                    },
++                    {
++                        "dataset": "market-data-normalized",
++                        "version_id": normalized_version_id,
++                        "content": normalized_content,
++                        "parent_version_id": raw_version_id,
++                    },
++                ],
+             )
+         except HistoricalDailyIngestionError:
+             self._rollback(raw_version_id, normalized_version_id)
+             raise
+         except Exception as error:
+             self._rollback(raw_version_id, normalized_version_id)
+             raise HistoricalDailyIngestionError(str(error)) from error
+         return HistoricalDailyIngestionResult(bars, raw_version_id, normalized_version_id)
+ 
+     @staticmethod
+@@ -119,29 +119,38 @@ class HistoricalDailyIngestionWorker:
+         source_id: str,
+     ) -> dict[str, Any]:
+         if not isinstance(raw_response, bytes):
+             raise HistoricalDailyIngestionError("历史日线读取器必须返回字节")
+         try:
+             payload = json.loads(raw_response)
+         except (UnicodeDecodeError, json.JSONDecodeError) as error:
+             raise HistoricalDailyIngestionError("历史日线原始响应无法解析") from error
+         if not isinstance(payload, dict) or not isinstance(payload.get("bars"), list):
+             raise HistoricalDailyIngestionError("历史日线响应缺少完整 bars 字段")
+-        if (
+-            payload.get("source_id") != source_id
+-            or payload.get("market") != security_id.market.value
+-        ):
+-            raise HistoricalDailyIngestionError("历史日线来源或市场不一致")
++        expected_identity = {
++            "security_code": security_id.display_code,
++            "exchange": security_id.exchange,
++            "currency": security_id.currency,
++            "market": security_id.market.value,
++        }
++        if payload.get("source_id") != source_id:
++            raise HistoricalDailyIngestionError("历史日线来源不一致")
++        for field, expected_value in expected_identity.items():
++            if payload.get(field) != expected_value:
++                raise HistoricalDailyIngestionError(f"历史日线{field}与证券身份不一致")
+         if payload.get("collected_at") != collected_at.isoformat():
+             raise HistoricalDailyIngestionError("历史日线采集时间不一致")
+-        if not isinstance(payload.get("data_version"), str) or not payload["data_version"]:
+-            raise HistoricalDailyIngestionError("历史日线数据版本缺失")
++        if (
++            not isinstance(payload.get("source_data_version"), str)
++            or not payload["source_data_version"]
++        ):
++            raise HistoricalDailyIngestionError("历史日线上游数据版本缺失")
+         return payload
+ 
+     def _normalize_payload(
+         self,
+         payload: dict[str, Any],
+         collected_at: datetime,
+         security_id: InstrumentIdentity,
+         source_id: str,
+         normalized_version_id: str,
+     ) -> tuple[bytes, list[IngestedHistoricalDailyBar]]:
+@@ -150,71 +159,71 @@ class HistoricalDailyIngestionWorker:
+             records = [
+                 {
+                     "security_id": security_id,
+                     "trading_date": bar["trade_date"],
+                     "market_time": market_time,
+                     "open": bar["open"],
+                     "high": bar["high"],
+                     "low": bar["low"],
+                     "close": bar["close"],
+                     "volume": bar["volume"],
+-                    "currency": security_id.currency,
+-                    "adjustment_basis": "none",
++                    "currency": payload["currency"],
++                    "adjustment_basis": payload["adjustment_basis"],
+                     "source_id": source_id,
+                     "collected_at": collected_at,
+-                    "data_version": normalized_version_id,
++                    "source_data_version": payload["source_data_version"],
+                 }
+                 for bar in payload["bars"]
+             ]
+-            normalized = HistoricalDailyBarBatch(self._versioning_service).normalize_and_save(
+-                records
+-            )
++            normalized = HistoricalDailyBarBatch().normalize(records)
+         except (KeyError, TypeError, ValueError, HistoricalDailyBarValidationError) as error:
+             raise HistoricalDailyIngestionError(f"历史日线字段或价格无效：{error}") from error
+         bars = [
+             IngestedHistoricalDailyBar(
+                 security_id=bar.security_id,
+                 trade_date=bar.trade_date,
+                 market_time=bar.market_time,
+                 open=bar.open,
+                 high=bar.high,
+                 low=bar.low,
+                 close=bar.close,
+                 volume=bar.volume,
+                 currency=bar.currency,
+                 adjustment_basis=bar.adjustment_basis,
+                 source_id=bar.source_id,
+                 collected_at=bar.collected_at,
+-                data_version=bar.data_version,
++                source_data_version=bar.source_data_version,
+             )
+             for bar in normalized
+         ]
+         document = {
+             "source_id": source_id,
+             "market": security_id.market.value,
+             "market_time": payload["market_time"],
+             "collected_at": collected_at.isoformat(),
+-            "data_version": normalized_version_id,
++            "source_data_version": payload["source_data_version"],
++            "artifact_version_id": normalized_version_id,
+             "bars": [
+                 {
+                     "trade_date": bar.trade_date.isoformat(),
+                     "market_time": bar.market_time.isoformat(),
+                     "open": bar.open,
+                     "high": bar.high,
+                     "low": bar.low,
+                     "close": bar.close,
+                     "volume": bar.volume,
+                     "currency": bar.currency,
+                     "adjustment_basis": bar.adjustment_basis,
+                     "source_id": bar.source_id,
+                     "collected_at": bar.collected_at.isoformat(),
+-                    "data_version": bar.data_version,
++                    "source_data_version": bar.source_data_version,
++                    "artifact_version_id": normalized_version_id,
+                     "freshness": bar.freshness.state,
+                 }
+                 for bar in bars
+             ],
+         }
+         return json.dumps(
+             document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
+         ).encode("utf-8"), bars
+ 
+     def _rollback(self, raw_version_id: str, normalized_version_id: str) -> None:
+diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
+index b2e3aaf..48e18a0 100644
+--- a/tests/failure/test_market_data_failures.py
++++ b/tests/failure/test_market_data_failures.py
+@@ -120,21 +120,21 @@ def test_新浪适配器响应缺少任一请求代码时拒绝全部行情(loca
+         "market_time",
+         "open",
+         "high",
+         "low",
+         "close",
+         "volume",
+         "currency",
+         "adjustment_basis",
+         "source_id",
+         "collected_at",
+-        "data_version",
++        "source_data_version",
+     ],
+ )
+ def test_标准化历史日线缺少任一契约字段时整批拒绝且不产生持久化记录(
+     缺失字段: str, local_data_root: Path
+ ) -> None:
+     """以公开标准化日线契约校验字段，不依赖特定供应商原始响应位置。"""
+ 
+     from stock_agent.application.historical_market_data import (
+         HistoricalDailyBarBatch,
+         HistoricalDailyBarValidationError,
+@@ -146,28 +146,28 @@ def test_标准化历史日线缺少任一契约字段时整批拒绝且不产
+         "market_time": datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
+         "open": 10.0,
+         "high": 10.3,
+         "low": 9.9,
+         "close": 10.2,
+         "volume": 1000,
+         "currency": "CNY",
+         "adjustment_basis": "none",
+         "source_id": "test-source",
+         "collected_at": datetime(2026, 7, 14, 15, 1, tzinfo=UTC),
+-        "data_version": "daily-v1",
++        "source_data_version": "daily-v1",
+     }
+     不完整日线 = 完整日线.copy()
+     del 不完整日线[缺失字段]
+ 
+-    批次 = HistoricalDailyBarBatch(VersioningService(local_data_root))
++    批次 = HistoricalDailyBarBatch()
+     with pytest.raises(HistoricalDailyBarValidationError, match="缺失|完整"):
+-        批次.normalize_and_save([完整日线, 不完整日线])
++        批次.normalize([完整日线, 不完整日线])
+ 
+     assert not (local_data_root / "artifacts" / "market-data-raw").exists()
+     assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
+ 
+ 
+ @pytest.mark.parametrize("状态", ["DELAYED", "STALE", "CLOSED"])
+ def test_当前预测拒绝过期或休市行情并给出不可用原因(状态: str) -> None:
+     """当前预测入口必须把不可用原因显式反馈给调用方，不能只返回裸布尔值。"""
+ 
+     with pytest.raises(FreshnessClassificationError, match="过期|不可用"):
+@@ -242,23 +242,21 @@ def test_公司行动拒绝不合法复权比例(复权比例: float) -> None:
+         )
+ 
+ 
+ @pytest.mark.parametrize(
+     ("action_id", "effective_at"),
+     [
+         ("", datetime(2026, 7, 14, 9, 0, tzinfo=UTC)),
+         ("split-20260714", datetime(2026, 7, 14, 9, 0)),
+     ],
+ )
+-def test_公司行动拒绝缺失标识或无时区日期(
+-    action_id: str, effective_at: datetime
+-) -> None:
++def test_公司行动拒绝缺失标识或无时区日期(action_id: str, effective_at: datetime) -> None:
+     """公司行动的标识和生效时点均是可追溯复权的最小前提。"""
+ 
+     with pytest.raises(ValueError, match="标识|时区"):
+         CompanyAction(
+             action_id=action_id,
+             action_type="split",
+             effective_at=effective_at,
+             version_id="v1",
+             source_id="test-source",
+         )
+diff --git a/tests/integration/test_sina_market_data_provenance.py b/tests/integration/test_sina_market_data_provenance.py
+index db15db0..8712a73 100644
+--- a/tests/integration/test_sina_market_data_provenance.py
++++ b/tests/integration/test_sina_market_data_provenance.py
+@@ -45,20 +45,45 @@ def test_新浪响应和规范化结果以同一版本关联追加保存(local_d
+     assert b'"market_time"' in normalized
+     assert b'"collected_at"' in normalized
+     assert (
+         service.metadata_for("market-data-normalized", normalized_versions[0].name)[
+             "parent_version_id"
+         ]
+         == raw_versions[0].name
+     )
+ 
+ 
++def test_新浪记录器规范化工件写入失败时原始和规范化均不残留(
++    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
++) -> None:
++    """真实记录器必须将一对工件作为同一批次发布，失败时不得留下半批次。"""
++
++    service = VersioningService(local_data_root)
++    原写入 = service._artifacts.write_artifact
++
++    def 拒绝规范化工件(dataset: str, *参数: object, **关键字参数: object):
++        if dataset == "market-data-normalized":
++            raise OSError("规范化工件写入失败")
++        return 原写入(dataset, *参数, **关键字参数)
++
++    monkeypatch.setattr(service._artifacts, "write_artifact", 拒绝规范化工件)
++
++    with pytest.raises(OSError, match="规范化工件写入失败"):
++        SinaMarketDataFactRecorder(service).record(新浪响应(), b'{"quotes":[]}')
++
++    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
++    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
++    assert service._metadata._connection.execute(
++        "SELECT COUNT(*) FROM dataset_versions"
++    ).fetchone() == (0,)
++
++
+ def test_新浪事实保存失败时不返回未持久化行情(local_data_root: Path) -> None:
+     """事实链提交失败必须使整批读取失败，不能把内存结果冒充事实。"""
+ 
+     class 失败记录器:
+         def record(self, raw_response: bytes, quotes: list[object]) -> None:
+             raise RuntimeError("本地保存失败")
+ 
+     adapter = SinaHttpAdapter(
+         lambda _url: 新浪响应(),
+         fact_recorder=失败记录器(),
+diff --git a/tests/integration/test_single_market_daily_pipeline.py b/tests/integration/test_single_market_daily_pipeline.py
+index 9fa3c66..53e7584 100644
+--- a/tests/integration/test_single_market_daily_pipeline.py
++++ b/tests/integration/test_single_market_daily_pipeline.py
+@@ -23,25 +23,29 @@ def 固定历史日线响应() -> bytes:
+                 {
+                     "close": 10.20,
+                     "high": 10.50,
+                     "low": 9.80,
+                     "open": 10.00,
+                     "trade_date": "2026-07-13",
+                     "volume": 1_000_000,
+                 }
+             ],
+             "collected_at": "2026-07-14T07:01:02+00:00",
+-            "data_version": "sina-固定历史响应-1",
++            "source_data_version": "sina-固定历史响应-1",
++            "adjustment_basis": "none",
++            "currency": "CNY",
++            "exchange": "SSE",
+             "market": "CN",
+             "market_time": "2026-07-13T15:00:00+08:00",
+             "response_schema_version": "固定历史日线响应-1",
+             "source_id": "sina",
++            "security_code": "600000",
+         },
+         ensure_ascii=False,
+         separators=(",", ":"),
+         sort_keys=True,
+     ).encode("utf-8")
+ 
+ 
+ def 创建工作者(读取历史日线, 服务: VersioningService):
+     """延迟导入尚未实现的工作者，使红灯直接指向 US1 的生产缺口。"""
+ 
+@@ -93,58 +97,57 @@ def test_历史日线将注入响应追加保存为原始与规范化工件并
+     assert 结果.bars[0].source_id == "sina"
+     assert 结果.bars[0].freshness.state != "REALTIME"
+     原始工件 = 服务.read_bytes("market-data-raw", 结果.raw_version_id)
+     原始批次 = json.loads(原始工件)
+     原始元数据 = 服务.metadata_for("market-data-raw", 结果.raw_version_id)
+     assert 原始工件 == 原始响应
+     assert 原始批次["source_id"] == "sina"
+     assert 原始批次["market"] == "CN"
+     assert 原始批次["market_time"] == "2026-07-13T15:00:00+08:00"
+     assert 原始批次["collected_at"] == "2026-07-14T07:01:02+00:00"
+-    assert 原始批次["data_version"] == "sina-固定历史响应-1"
++    assert 原始批次["source_data_version"] == "sina-固定历史响应-1"
+     assert 原始元数据["content_hash"] == hashlib.sha256(原始工件).hexdigest()
+     assert 原始元数据["parent_version_id"] is None
+ 
+     规范化工件 = 服务.read_bytes("market-data-normalized", 结果.normalized_version_id)
+     规范化批次 = json.loads(规范化工件)
+     元数据 = 服务.metadata_for("market-data-normalized", 结果.normalized_version_id)
+     assert 规范化批次["source_id"] == "sina"
+     assert 规范化批次["market"] == "CN"
+     assert 规范化批次["collected_at"] == "2026-07-14T07:01:02+00:00"
+     assert 规范化批次["bars"][0]["market_time"] == "2026-07-13T15:00:00+08:00"
+-    assert 规范化批次["bars"][0]["data_version"] == 结果.normalized_version_id
+-    assert 规范化批次["data_version"] == 结果.normalized_version_id
++    assert 规范化批次["bars"][0]["source_data_version"] == "sina-固定历史响应-1"
++    assert 规范化批次["bars"][0]["adjustment_basis"] == "none"
++    assert 规范化批次["bars"][0]["artifact_version_id"] == 结果.normalized_version_id
++    assert 规范化批次["source_data_version"] == "sina-固定历史响应-1"
++    assert 规范化批次["artifact_version_id"] == 结果.normalized_version_id
+     assert 元数据["parent_version_id"] == 结果.raw_version_id
+     assert 元数据["content_hash"] == hashlib.sha256(规范化工件).hexdigest()
+ 
+ 
+ def test_相同历史响应重采集会追加可追溯新记录而非静默覆盖(
+     local_data_root: Path,
+ ) -> None:
+     """相同内容的再次采集必须产生新的原始和规范化版本，并保留各自父链。"""
+ 
+     服务 = VersioningService(local_data_root)
+     工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)
+ 
+     首次 = 工作者.collect_and_save(**采集参数())
+     第二次 = 工作者.collect_and_save(**采集参数())
+ 
+     assert 首次.raw_version_id != 第二次.raw_version_id
+     assert 首次.normalized_version_id != 第二次.normalized_version_id
+     assert 服务.read_bytes("market-data-raw", 首次.raw_version_id) == 固定历史日线响应()
++    assert 服务.read_bytes("market-data-raw", 第二次.raw_version_id) == 固定历史日线响应()
+     assert (
+-        服务.read_bytes("market-data-raw", 第二次.raw_version_id) == 固定历史日线响应()
+-    )
+-    assert (
+-        服务.metadata_for("market-data-normalized", 首次.normalized_version_id)[
+-            "parent_version_id"
+-        ]
++        服务.metadata_for("market-data-normalized", 首次.normalized_version_id)["parent_version_id"]
+         == 首次.raw_version_id
+     )
+     assert (
+         服务.metadata_for("market-data-normalized", 第二次.normalized_version_id)[
+             "parent_version_id"
+         ]
+         == 第二次.raw_version_id
+     )
+ 
+ 
+@@ -173,28 +176,28 @@ def test_任一日线字段非法时原始与规范化两侧均不留下半批
+ 
+ @pytest.mark.parametrize("失败数据集", ["market-data-raw", "market-data-normalized"])
+ def test_任一工件保存失败时历史日线原子回滚且报告失败原因(
+     失败数据集: str, local_data_root: Path, monkeypatch: pytest.MonkeyPatch
+ ) -> None:
+     """两侧工件必须作为一个批次提交；任一保存失败均不可留下可见版本。"""
+ 
+     from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError
+ 
+     服务 = VersioningService(local_data_root)
+-    原提交 = 服务.commit_bytes
++    原提交 = 服务.commit_batch
+ 
+-    def 失败提交(*, dataset: str, **参数: object):
+-        if dataset == 失败数据集:
++    def 失败提交(*, items: list[dict[str, object]], **参数: object):
++        if any(item["dataset"] == 失败数据集 for item in items):
+             raise OSError(f"{失败数据集} 保存失败")
+-        return 原提交(dataset=dataset, **参数)
++        return 原提交(items=items, **参数)
+ 
+-    monkeypatch.setattr(服务, "commit_bytes", 失败提交)
++    monkeypatch.setattr(服务, "commit_batch", 失败提交)
+     工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)
+ 
+     with pytest.raises(HistoricalDailyIngestionError, match="保存失败"):
+         工作者.collect_and_save(**采集参数())
+ 
+     断言不存在半批工件或元数据(服务, local_data_root)
+ 
+ 
+ @pytest.mark.parametrize("失败数据集", ["market-data-raw", "market-data-normalized"])
+ @pytest.mark.parametrize("失败时点", ["元数据登记", "完成标记"])
+@@ -230,37 +233,88 @@ def test_工件字节写入后元数据登记或完成标记失败时两侧零
+             (目录 / "manifest.json").write_text(
+                 json.dumps({"content_hash": hashlib.sha256(content).hexdigest()}),
+                 encoding="utf-8",
+             )
+             raise OSError(f"{失败数据集} 完成标记失败")
+ 
+         monkeypatch.setattr(服务._artifacts, "write_artifact", 完成标记前失败)
+ 
+     工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)
+ 
+-    with pytest.raises(
+-        HistoricalDailyIngestionError, match="元数据登记失败|完成标记失败"
+-    ):
++    with pytest.raises(HistoricalDailyIngestionError, match="元数据登记失败|完成标记失败"):
+         工作者.collect_and_save(**采集参数())
+ 
+     断言不存在半批工件或元数据(服务, local_data_root)
+ 
+ 
+ def test_历史日线不得作为当前预测的实时输入(local_data_root: Path) -> None:
+     """闭环产物只能用于历史研究；即使日线完整也必须被当前预测入口拒绝。"""
+ 
+     服务 = VersioningService(local_data_root)
+-    结果 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务).collect_and_save(
+-        **采集参数()
+-    )
+-
++    结果 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务).collect_and_save(**采集参数())
+     assert (
+         is_usable_for_current_prediction(
+             {
+                 "collected_at": 结果.bars[0].collected_at,
+                 "market_time": 结果.bars[0].market_time,
+                 "state": "CLOSED",
+                 "time_is_verifiable": True,
+             }
+         )
+         is False
+     )
++
++
++@pytest.mark.parametrize(
++    ("字段", "错误值"),
++    [
++        ("security_code", "000001"),
++        ("exchange", "SZSE"),
++        ("currency", "USD"),
++        ("market", "US"),
++    ],
++)
++def test_payload_证券身份任一字段与调用身份不一致时整批拒绝且零残留(
++    字段: str, 错误值: str, local_data_root: Path
++) -> None:
++    """供应商载荷必须显式复核证券代码、交易所、币种和市场。"""
++
++    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError
++
++    payload = json.loads(固定历史日线响应())
++    payload[字段] = 错误值
++    服务 = VersioningService(local_data_root)
++    工作者 = 创建工作者(
++        lambda **_参数: json.dumps(payload, ensure_ascii=False).encode("utf-8"), 服务
++    )
++
++    with pytest.raises(HistoricalDailyIngestionError, match="证券|市场|交易所|币种"):
++        工作者.collect_and_save(**采集参数())
++
++    断言不存在半批工件或元数据(服务, local_data_root)
++
++
++def test_批次完成标记失败时两侧均不可查询且下次启动会恢复(
++    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
++) -> None:
++    """唯一批次完成标记失败不能把任一侧暴露为独立版本。"""
++
++    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError
++
++    服务 = VersioningService(local_data_root)
++    原触碰 = Path.touch
++
++    def 拒绝批次完成标记(path: Path, *参数: object, **关键字参数: object) -> None:
++        if path.name == "_COMPLETE" and ".batches" in path.parts:
++            raise OSError("批次完成标记失败")
++        原触碰(path, *参数, **关键字参数)
++
++    monkeypatch.setattr(Path, "touch", 拒绝批次完成标记)
++    with pytest.raises(HistoricalDailyIngestionError, match="批次完成标记失败"):
++        创建工作者(lambda **_参数: 固定历史日线响应(), 服务).collect_and_save(**采集参数())
++
++    assert list((local_data_root / "artifacts").rglob("_COMPLETE")) == []
++    assert 服务._metadata._connection.execute(
++        "SELECT COUNT(*) FROM dataset_versions"
++    ).fetchone() == (0,)
++    恢复后服务 = VersioningService(local_data_root)
++    断言不存在半批工件或元数据(恢复后服务, local_data_root)
+diff --git a/tests/integration/test_versioning_atomic_commit.py b/tests/integration/test_versioning_atomic_commit.py
+new file mode 100644
+index 0000000..23c0ef5
+--- /dev/null
++++ b/tests/integration/test_versioning_atomic_commit.py
+@@ -0,0 +1,101 @@
++"""验证原始行情与预测快照只能追加写入，失败暂存不会污染已验证版本。"""
++
++from pathlib import Path
++
++import pytest
++
++
++def test_版本提交保留父版本且拒绝静默覆盖(local_data_root: Path) -> None:
++    """同一版本标识不能覆盖既有事实，修订必须显式引用父版本。"""
++
++    from stock_agent.application.versioning_service import ImmutableVersionError, VersioningService
++
++    service = VersioningService(local_data_root)
++    original = service.commit_bytes(
++        dataset="daily-bars",
++        version_id="v1",
++        content=b"first",
++        source_id="test-source",
++    )
++    revised = service.commit_bytes(
++        dataset="daily-bars",
++        version_id="v2",
++        content=b"revised",
++        source_id="test-source",
++        parent_version_id="v1",
++        revision_reason="修订来源字段",
++    )
++
++    assert original.parent_version_id is None
++    assert revised.parent_version_id == "v1"
++    assert service.read_bytes("daily-bars", "v1") == b"first"
++
++    with pytest.raises(ImmutableVersionError):
++        service.commit_bytes(
++            dataset="daily-bars", version_id="v1", content=b"overwrite", source_id="test-source"
++        )
++
++
++def test_暂存校验失败不产生可见版本(local_data_root: Path) -> None:
++    """不完整暂存工件不能被登记为已提交版本。"""
++
++    from stock_agent.application.versioning_service import VersioningService
++
++    service = VersioningService(local_data_root)
++
++    with pytest.raises(ValueError, match="哈希"):
++        service.commit_bytes(
++            dataset="daily-bars",
++            version_id="v1",
++            content=b"payload",
++            source_id="test-source",
++            expected_hash="0" * 64,
++        )
++
++    assert not service.version_exists("daily-bars", "v1")
++
++
++def test_提交版本必须登记元数据并写入完成标记(local_data_root: Path) -> None:
++    """版本链只有在工件完成与 DuckDB 元数据同时存在时才可供查询。"""
++
++    from stock_agent.application.versioning_service import VersioningService
++
++    service = VersioningService(local_data_root)
++    committed = service.commit_bytes(
++        dataset="daily-bars", version_id="v1", content=b"payload", source_id="test-source"
++    )
++
++    assert (local_data_root / "artifacts" / "daily-bars" / "v1" / "_COMPLETE").is_file()
++    assert service.metadata_for("daily-bars", "v1")["content_hash"] == committed.content_hash
++
++
++@pytest.mark.parametrize("损坏内容", ['{"entries":[', "{}"])
++def test_启动恢复损坏批次日志时清理元数据和双方工件(local_data_root: Path, 损坏内容: str) -> None:
++    """截断日志不得阻断初始化，已登记的未完成批次必须被安全清理。"""
++
++    from stock_agent.application.versioning_service import VersioningService
++
++    service = VersioningService(local_data_root)
++    batch_id = "损坏日志批次"
++    batch_directory = local_data_root / ".batches" / batch_id
++    batch_directory.mkdir(parents=True)
++    batch_directory.joinpath("manifest.json").write_text(损坏内容, encoding="utf-8")
++    for dataset, version_id in (
++        ("market-data-raw", "raw-1"),
++        ("market-data-normalized", "normalized-1"),
++    ):
++        artifact = service._artifacts.write_artifact(
++            dataset, version_id, b"payload", complete=False
++        )
++        service._metadata.register_batch_version(
++            batch_id, dataset, version_id, artifact.content_hash, None
++        )
++
++    recovered = VersioningService(local_data_root)
++
++    assert not batch_directory.exists()
++    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
++    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
++    assert recovered._metadata._connection.execute(
++        "SELECT COUNT(*) FROM dataset_versions"
++    ).fetchone() == (0,)
+
+```
+
diff --git a/.superpowers/sdd/task-040-fix-report.md b/.superpowers/sdd/task-040-fix-report.md
new file mode 100644
index 0000000..3bd3826
--- /dev/null
+++ b/.superpowers/sdd/task-040-fix-report.md
@@ -0,0 +1,55 @@
+# T040 独立审查问题修复报告
+
+## 修复结果
+
+- `VersioningService.commit_batch()` 为原始和规范化工件建立同一批次日志；两侧先写入无 `_COMPLETE` 的暂存工件并登记元数据，最后只在 `.batches/<batch_id>/_COMPLETE` 写入单一完成标记。
+- `version_exists()`、`read_bytes()` 与 `metadata_for()` 仅将单版本完成工件或含单一批次完成标记的批次成员视为可见。批次中断、完成标记失败或补偿失败均不会让任一侧独立可查询。
+- 服务初始化会扫描未完成批次日志，幂等删除工件目录和 DuckDB 元数据，作为进程中断或补偿失败后的恢复策略。
+- 标准化接口改为准确的 `HistoricalDailyBarBatch.normalize()`，仅执行全批校验和标准化；持久化只能由受控的 `HistoricalDailyIngestionWorker` 完成。
+- 规范化产物保留 `source_data_version`、`adjustment_basis` 和本地 `artifact_version_id`，不再使用本地 UUID 覆盖上游来源版本。
+- 载荷必须显式携带并匹配 `security_code`、`exchange`、`currency`、`market`；任一不匹配会整批拒绝且不留可见工件或元数据。
+
+## TDD 红灯与绿灯
+
+先新增并运行以下回归测试，红灯分别证明旧实现缺少来源版本保留、未核验代码/交易所/币种，以及存在两侧独立完成标记：
+
+- 批次唯一完成标记失败时两侧均不可查询，并在下次启动恢复。
+- 上游证券代码、交易所、币种、市场任一不匹配时整批拒绝。
+- 规范化工件同时保存上游版本、复权口径和本地产物版本。
+
+实现后，以下相关组合测试通过：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py -v
+```
+
+结果：`27 passed`。
+
+按任务指定组合运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -q
+```
+
+结果：`52 passed, 14 failed`。14 项均为本任务范围外的既有缺口：当前预测新鲜度拒绝、跨市场证券身份校验、代码歧义解析、公司行动与复权规则；未涉及本次批次提交路径。
+
+## 质量检查
+
+```powershell
+py -3.12 -m ruff format --check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py src/stock_agent/adapters/storage/parquet_store.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py
+py -3.12 -m ruff check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py src/stock_agent/adapters/storage/parquet_store.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py
+py -3.12 tools/check_chinese_project_text.py
+```
+
+三项检查均通过。
+
+全量命令 `py -3.12 -m pytest -o addopts='' -q` 在收集阶段被既有缺失模块阻断：
+
+- `stock_agent.desktop.pages.market_page`
+- `stock_agent.application.market_service`
+
+因此未能进入完整测试执行；该阻断与本次修改无关。
+
+## 风险与恢复边界
+
+批次完成标记写入前，即使原始或规范化目录、元数据已经存在，也不会被本服务的查询接口视为可见版本；启动恢复会清除未完成批次。单一完成标记写入后两侧同时公开。当前实现依赖所有调用方通过 `VersioningService` 查询，不应绕过服务直接枚举 `artifacts` 目录并将无完成标记目录当作有效版本。
diff --git a/.superpowers/sdd/task-040-fix2-report.md b/.superpowers/sdd/task-040-fix2-report.md
new file mode 100644
index 0000000..5d66503
--- /dev/null
+++ b/.superpowers/sdd/task-040-fix2-report.md
@@ -0,0 +1,41 @@
+# T040 原子发布第二轮修复报告
+
+## 修复结果
+
+- `SinaMarketDataFactRecorder` 已改为一次调用 `VersioningService.commit_batch()` 发布原始响应与规范化事实；任一工件写入失败时，批次回滚原始工件、规范化工件和两者元数据，不产生单侧 `_COMPLETE`。
+- 批次 journal 先写入同目录临时文件，再以替换操作发布 `manifest.json`，避免直接覆盖留下截断内容。
+- DuckDB 增加批次成员恢复索引。启动恢复将 JSON 截断、缺少 `entries` 或条目结构无效的 journal 都视为未完成批次，以恢复索引和可解析日志的并集清理工件与元数据，不让 JSON 解析异常阻断初始化。
+- 未改变历史日线 worker 的 `commit_batch()` 使用方式、来源时点字段或版本语义；测试全程没有真实网络或交易。
+
+## TDD 证据
+
+- 先新增真实 Sina 记录器的规范化工件写入失败回归：旧实现失败后仍保留 `market-data-raw`。
+- 先新增损坏 journal 恢复回归：旧实现缺少批次恢复索引；补充 `{}` 合法但结构损坏场景后，旧实现因 `KeyError: 'entries'` 阻断初始化。
+- 最小实现后，两类回归均转绿。
+
+## 验证结果
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -q
+```
+
+结果：`65 passed, 14 failed`。14 项均为既有且不属于本次批次发布路径的市场规则、当前预测新鲜度和公司行动缺口。
+
+```powershell
+py -3.12 -m pytest -o addopts='' -q
+```
+
+全量在收集阶段被既有缺失模块阻断：`stock_agent.desktop.pages.market_page` 与 `stock_agent.application.market_service`。
+
+```powershell
+py -3.12 -m ruff format --check src/stock_agent/adapters/market_data/sina_provenance.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/application/versioning_service.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_versioning_atomic_commit.py
+py -3.12 -m ruff check src/stock_agent/adapters/market_data/sina_provenance.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/application/versioning_service.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_versioning_atomic_commit.py
+py -3.12 tools/check_chinese_project_text.py
+```
+
+三项检查通过。
+
+## 风险边界
+
+- 批次完成标记写入前，版本服务不会把任一成员视为可见；启动恢复会清理未完成或日志无效的批次。
+- 损坏日志恢复依赖批次成员恢复索引；该索引在每个成员的元数据登记时写入，覆盖已登记的双侧残留。
diff --git a/.superpowers/sdd/task-040-fix3-report.md b/.superpowers/sdd/task-040-fix3-report.md
new file mode 100644
index 0000000..db08064
--- /dev/null
+++ b/.superpowers/sdd/task-040-fix3-report.md
@@ -0,0 +1,42 @@
+# T040 最终审查原子性修复报告
+
+## 修复结果
+
+- 单工件 `commit_bytes()` 现在先建立带完整恢复清单的暂存批次，写入未完成工件并登记元数据，最后依次公开工件完成标记与批次完成标记。查询接口同时校验完成证据和元数据，因此任一中断阶段均不会读取半提交。
+- 每个暂存批次在写入工件前原子落盘 `recovery.json`；恢复以该清单为权威。空条目 journal 被拒绝，截断、损坏或空 journal 即使发生在 `batch_versions` 尚未登记时，也会清理工件目录、`dataset_versions` 和 `batch_versions`，且不会阻断启动。
+- 历史 normalized 载荷及其每条 bar 均保留完整证券身份：`market`、`security_code`、`display_code`、`exchange`、`currency`。原始与规范化工件仍通过 `commit_batch()` 成对提交。
+
+## TDD 证据
+
+先新增并确认以下测试红灯：
+
+- 单工件完成标记失败后，旧实现会遗留数据集目录；
+- 损坏或空 journal 且批次索引未登记时，旧实现无法根据暂存目录清理工件；
+- normalized 载荷回读时，旧实现缺少 `security_code` 等完整身份字段。
+
+实现后相关回归转绿：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py tests/integration/test_single_market_daily_pipeline.py tests/integration/test_sina_market_data_provenance.py -q
+```
+
+结果：`34 passed`。
+
+## 质量检查
+
+```powershell
+py -3.12 -m ruff format --check src/stock_agent/application/versioning_service.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/workers/market_ingestion.py tests/integration/test_versioning_atomic_commit.py tests/integration/test_single_market_daily_pipeline.py
+py -3.12 -m ruff check src/stock_agent/application/versioning_service.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/workers/market_ingestion.py tests/integration/test_versioning_atomic_commit.py tests/integration/test_single_market_daily_pipeline.py
+py -3.12 tools/check_chinese_project_text.py
+```
+
+三项检查均通过。
+
+## 全量测试阻断
+
+全量命令 `py -3.12 -m pytest -o addopts='' -q` 在收集阶段被既有缺失模块阻断，尚未执行到测试主体：
+
+- `stock_agent.desktop.pages.market_page`
+- `stock_agent.application.market_service`
+
+本次未引入真实网络请求或交易行为。
diff --git a/src/stock_agent/adapters/market_data/sina_provenance.py b/src/stock_agent/adapters/market_data/sina_provenance.py
index 73ead60..17ea4be 100644
--- a/src/stock_agent/adapters/market_data/sina_provenance.py
+++ b/src/stock_agent/adapters/market_data/sina_provenance.py
@@ -11,38 +11,43 @@ from stock_agent.application.versioning_service import VersioningService
 
 class SinaMarketDataFactRecorder:
     """使用版本服务追加保存一批新浪原始响应及其规范化结果。"""
 
     def __init__(self, versioning_service: VersioningService) -> None:
         """注入项目既有版本服务，避免行情适配器另建存储体系。"""
 
         self._versioning_service = versioning_service
 
     def record(self, raw_response: bytes, normalized_content: bytes) -> SinaPersistenceProof:
-        """先提交原始字节，再原样提交适配器提供的规范化事实载荷。"""
+        """以同一批次公开原始字节和规范化事实载荷。"""
 
         if not normalized_content:
             raise ValueError("规范化事实载荷不能为空")
         raw_hash = hashlib.sha256(raw_response).hexdigest()
         suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f%z")
         version_prefix = raw_hash[:16]
         raw_version_id = f"sina-{version_prefix}-raw-{suffix}"
-        raw = self._versioning_service.commit_bytes(
-            dataset="market-data-raw",
-            version_id=raw_version_id,
-            content=raw_response,
-            source_id="sina",
-            expected_hash=raw_hash,
-        )
         normalized_version_id = f"sina-{version_prefix}-normalized-{suffix}"
-        normalized = self._versioning_service.commit_bytes(
-            dataset="market-data-normalized",
-            version_id=normalized_version_id,
-            content=normalized_content,
-            source_id="sina",
-            parent_version_id=raw.version_id,
+        raw, normalized = self._versioning_service.commit_batch(
+            batch_id=f"sina-{version_prefix}-{suffix}",
+            items=[
+                {
+                    "dataset": "market-data-raw",
+                    "version_id": raw_version_id,
+                    "content": raw_response,
+                    "source_id": "sina",
+                    "expected_hash": raw_hash,
+                },
+                {
+                    "dataset": "market-data-normalized",
+                    "version_id": normalized_version_id,
+                    "content": normalized_content,
+                    "source_id": "sina",
+                    "parent_version_id": raw_version_id,
+                },
+            ],
         )
         return SinaPersistenceProof(
             raw_artifact_version_id=raw.version_id,
             normalized_artifact_version_id=normalized.version_id,
             parent_version_id=normalized.parent_version_id or "",
         )
diff --git a/src/stock_agent/adapters/storage/duckdb_store.py b/src/stock_agent/adapters/storage/duckdb_store.py
new file mode 100644
index 0000000..9d0ed4c
--- /dev/null
+++ b/src/stock_agent/adapters/storage/duckdb_store.py
@@ -0,0 +1,81 @@
+"""使用 DuckDB 追加登记已提交的数据版本。"""
+
+from pathlib import Path
+
+import duckdb
+
+
+class DuckDbMetadataStore:
+    """将版本元数据置于事务中，避免工件可见但版本链缺失。"""
+
+    def __init__(self, database_path: Path) -> None:
+        self._connection = duckdb.connect(str(database_path))
+        self._connection.execute(
+            "CREATE TABLE IF NOT EXISTS dataset_versions ("
+            "dataset VARCHAR, version_id VARCHAR, content_hash VARCHAR, "
+            "parent_version_id VARCHAR, PRIMARY KEY(dataset, version_id))"
+        )
+        self._connection.execute(
+            "CREATE TABLE IF NOT EXISTS batch_versions ("
+            "batch_id VARCHAR, dataset VARCHAR, version_id VARCHAR, "
+            "PRIMARY KEY(batch_id, dataset, version_id))"
+        )
+
+    def register_version(
+        self, dataset: str, version_id: str, content_hash: str, parent_version_id: str | None
+    ) -> None:
+        """原子登记一个不可覆盖的数据版本。"""
+        self._connection.execute(
+            "INSERT INTO dataset_versions VALUES (?, ?, ?, ?)",
+            [dataset, version_id, content_hash, parent_version_id],
+        )
+
+    def register_batch_version(
+        self,
+        batch_id: str,
+        dataset: str,
+        version_id: str,
+        content_hash: str,
+        parent_version_id: str | None,
+    ) -> None:
+        """登记未完成批次成员，供损坏日志的启动恢复定位残留。"""
+        self.register_version(dataset, version_id, content_hash, parent_version_id)
+        self._connection.execute(
+            "INSERT INTO batch_versions VALUES (?, ?, ?)",
+            [batch_id, dataset, version_id],
+        )
+
+    def batch_versions(self, batch_id: str) -> list[tuple[str, str]]:
+        """返回批次已登记成员，不依赖磁盘日志的可解析性。"""
+        return [
+            (row[0], row[1])
+            for row in self._connection.execute(
+                "SELECT dataset, version_id FROM batch_versions WHERE batch_id = ?",
+                [batch_id],
+            ).fetchall()
+        ]
+
+    def delete_batch_versions(self, batch_id: str) -> None:
+        """删除已回滚批次的恢复索引。"""
+        self._connection.execute("DELETE FROM batch_versions WHERE batch_id = ?", [batch_id])
+
+    def get_version(self, dataset: str, version_id: str) -> dict[str, str | None]:
+        """读取指定版本，不隐式返回最新版本。"""
+        row = self._connection.execute(
+            "SELECT content_hash, parent_version_id FROM dataset_versions "
+            "WHERE dataset = ? AND version_id = ?",
+            [dataset, version_id],
+        ).fetchone()
+        if row is None:
+            raise KeyError(version_id)
+        return {"content_hash": row[0], "parent_version_id": row[1]}
+
+    def has_version(self, dataset: str, version_id: str) -> bool:
+        """确认元数据已登记，避免仅凭完成标记暴露半提交工件。"""
+        return (
+            self._connection.execute(
+                "SELECT 1 FROM dataset_versions WHERE dataset = ? AND version_id = ?",
+                [dataset, version_id],
+            ).fetchone()
+            is not None
+        )
diff --git a/src/stock_agent/adapters/storage/parquet_store.py b/src/stock_agent/adapters/storage/parquet_store.py
new file mode 100644
index 0000000..8d00935
--- /dev/null
+++ b/src/stock_agent/adapters/storage/parquet_store.py
@@ -0,0 +1,37 @@
+"""保存带哈希、清单和完成标记的不可变工件目录。"""
+
+import hashlib
+import json
+from dataclasses import dataclass
+from pathlib import Path
+
+
+@dataclass(frozen=True, slots=True)
+class StoredArtifact:
+    """描述已完成的不可变工件。"""
+
+    content_hash: str
+    complete_marker: Path
+
+
+class ParquetArtifactStore:
+    """为后续 Parquet 行情和特征文件提供版本目录及完成证据。"""
+
+    def __init__(self, root: Path) -> None:
+        self._root = root
+
+    def write_artifact(
+        self, dataset: str, version_id: str, content: bytes, *, complete: bool = True
+    ) -> StoredArtifact:
+        """写入工件；批次提交时由统一完成标记决定可见性。"""
+        directory = self._root / dataset / version_id
+        directory.mkdir(parents=True, exist_ok=False)
+        digest = hashlib.sha256(content).hexdigest()
+        (directory / "payload.parquet").write_bytes(content)
+        (directory / "manifest.json").write_text(
+            json.dumps({"content_hash": digest}), encoding="utf-8"
+        )
+        marker = directory / "_COMPLETE"
+        if complete:
+            marker.touch()
+        return StoredArtifact(digest, marker)
diff --git a/src/stock_agent/application/historical_market_data.py b/src/stock_agent/application/historical_market_data.py
index 811c6f9..5f0fda8 100644
--- a/src/stock_agent/application/historical_market_data.py
+++ b/src/stock_agent/application/historical_market_data.py
@@ -1,20 +1,19 @@
 """历史日线的最小标准化契约。"""
 
 from __future__ import annotations
 
 import math
 from dataclasses import dataclass
 from datetime import date, datetime
 from typing import Any
 
-from stock_agent.application.versioning_service import VersioningService
 from stock_agent.domain.market import InstrumentIdentity, Market
 
 
 class HistoricalDailyBarValidationError(ValueError):
     """表示历史日线未满足完整、可追溯的标准化契约。"""
 
 
 @dataclass(frozen=True, slots=True)
 class HistoricalDailyBar:
     """已标准化的一条历史日线，明确不能作为实时行情使用。"""
@@ -24,47 +23,44 @@ class HistoricalDailyBar:
     market_time: datetime
     open: float
     high: float
     low: float
     close: float
     volume: float
     currency: str
     adjustment_basis: str
     source_id: str
     collected_at: datetime
-    data_version: str
+    source_data_version: str
 
 
 class HistoricalDailyBarBatch:
     """对整批历史日线执行先验证、后返回的标准化。"""
 
     _REQUIRED_FIELDS = {
         "security_id",
         "trading_date",
         "market_time",
         "open",
         "high",
         "low",
         "close",
         "volume",
         "currency",
         "adjustment_basis",
         "source_id",
         "collected_at",
-        "data_version",
+        "source_data_version",
     }
 
-    def __init__(self, versioning_service: VersioningService) -> None:
-        self._versioning_service = versioning_service
-
-    def normalize_and_save(self, records: list[dict[str, Any]]) -> list[HistoricalDailyBar]:
-        """验证完整批次并返回标准化结果；任一记录无效即拒绝整批。"""
+    def normalize(self, records: list[dict[str, Any]]) -> list[HistoricalDailyBar]:
+        """验证完整批次并返回标准化结果，不执行持久化。"""
         if not records:
             raise HistoricalDailyBarValidationError("历史日线批次不能为空")
         return [self._normalize(record) for record in records]
 
     def _normalize(self, record: dict[str, Any]) -> HistoricalDailyBar:
         missing = self._REQUIRED_FIELDS - record.keys()
         if missing or any(record[field] in (None, "") for field in self._REQUIRED_FIELDS - missing):
             raise HistoricalDailyBarValidationError("历史日线字段缺失或不完整")
 
         security_id = record["security_id"]
@@ -91,37 +87,40 @@ class HistoricalDailyBarBatch:
         volume = self._number(record["volume"], "成交量")
         if low > min(open_price, close) or high < max(open_price, close) or high < low:
             raise HistoricalDailyBarValidationError("日线价格区间无效")
         if volume < 0:
             raise HistoricalDailyBarValidationError("成交量不能为负数")
         if (
             not isinstance(record["adjustment_basis"], str)
             or not record["adjustment_basis"].strip()
         ):
             raise HistoricalDailyBarValidationError("复权口径无效")
-        if not isinstance(record["data_version"], str) or not record["data_version"].strip():
-            raise HistoricalDailyBarValidationError("数据版本无效")
+        if (
+            not isinstance(record["source_data_version"], str)
+            or not record["source_data_version"].strip()
+        ):
+            raise HistoricalDailyBarValidationError("上游数据版本无效")
 
         return HistoricalDailyBar(
             security_id=security_id,
             trade_date=trade_date,
             market_time=market_time,
             open=open_price,
             high=high,
             low=low,
             close=close,
             volume=volume,
             currency=record["currency"],
             adjustment_basis=record["adjustment_basis"],
             source_id=record["source_id"],
             collected_at=collected_at,
-            data_version=record["data_version"],
+            source_data_version=record["source_data_version"],
         )
 
     @staticmethod
     def _datetime(value: Any, label: str) -> datetime:
         if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
             raise HistoricalDailyBarValidationError(f"{label}必须包含时区")
         return value
 
     @staticmethod
     def _number(value: Any, label: str) -> float:
diff --git a/src/stock_agent/application/versioning_service.py b/src/stock_agent/application/versioning_service.py
index 198ee53..5c895a8 100644
--- a/src/stock_agent/application/versioning_service.py
+++ b/src/stock_agent/application/versioning_service.py
@@ -1,84 +1,283 @@
-"""通过暂存、校验和原子目录移动保存不可变版本。"""
+"""通过单一批次完成标记发布不可变版本，并在启动时恢复未完成批次。"""
 
 from __future__ import annotations
 
 import hashlib
+import json
+import shutil
+import uuid
 from dataclasses import dataclass
 from pathlib import Path
+from typing import Any
 
 from stock_agent.adapters.storage.duckdb_store import DuckDbMetadataStore
 from stock_agent.adapters.storage.parquet_store import ParquetArtifactStore
 
 
 class ImmutableVersionError(ValueError):
     """表示试图覆盖已经提交的量化事实版本。"""
 
 
 @dataclass(frozen=True, slots=True)
 class CommittedVersion:
     """描述已经校验并可被查询的版本链节点。"""
 
     dataset: str
     version_id: str
     parent_version_id: str | None
     content_hash: str
 
 
 class VersioningService:
-    """将暂存工件校验后一次性提交，失败时不改变任何已验证版本。"""
+    """以批次日志和唯一完成标记保证多工件不会独立对外可见。"""
 
     def __init__(self, data_root: Path) -> None:
         self._root = data_root
         self._artifacts = ParquetArtifactStore(data_root / "artifacts")
         self._metadata = DuckDbMetadataStore(data_root / "metadata.duckdb")
+        self._batches_root = data_root / ".batches"
+        self._recover_incomplete_batches()
 
     def version_exists(self, dataset: str, version_id: str) -> bool:
-        """判断指定版本是否已经提交。"""
-        return (self._root / "artifacts" / dataset / version_id / "_COMPLETE").is_file()
+        """只把单版本完成标记或已完成批次中的版本视为可查询。"""
+        if (
+            self._root / "artifacts" / dataset / version_id / "_COMPLETE"
+        ).is_file() and self._metadata.has_version(dataset, version_id):
+            return True
+        return self._completed_batch_contains(dataset, version_id)
 
     def commit_bytes(
         self,
         *,
         dataset: str,
         version_id: str,
         content: bytes,
         source_id: str,
         parent_version_id: str | None = None,
         revision_reason: str | None = None,
         expected_hash: str | None = None,
     ) -> CommittedVersion:
-        """校验暂存字节后提交新版本，禁止覆盖既有目录。"""
+        """提交单个既有工件；多工件必须改用 ``commit_batch``。"""
         if self.version_exists(dataset, version_id):
             raise ImmutableVersionError("已提交版本不允许静默覆盖")
-        digest = hashlib.sha256(content).hexdigest()
-        if expected_hash is not None and expected_hash != digest:
-            raise ValueError("暂存工件哈希校验失败")
-        artifact = self._artifacts.write_artifact(dataset, version_id, content)
-        self._metadata.register_version(
-            dataset, version_id, artifact.content_hash, parent_version_id
-        )
+        digest = self._validate_hash(content, expected_hash)
+        batch_id = f"single-{uuid.uuid4().hex}"
+        entries = [
+            {
+                "dataset": dataset,
+                "version_id": version_id,
+                "parent_version_id": parent_version_id,
+                "content_hash": digest,
+            }
+        ]
+        batch_directory = self._create_batch_directory(batch_id, entries)
+        try:
+            artifact = self._artifacts.write_artifact(dataset, version_id, content, complete=False)
+            self._metadata.register_batch_version(
+                batch_id, dataset, version_id, artifact.content_hash, parent_version_id
+            )
+            artifact.complete_marker.touch()
+            (batch_directory / "_COMPLETE").touch()
+        except Exception:
+            try:
+                self.rollback_batch(batch_id)
+            except Exception:
+                # 暂存清单会在下一次启动时清理，保留原始提交失败原因。
+                pass
+            raise
         return CommittedVersion(dataset, version_id, parent_version_id, digest)
 
+    def commit_batch(self, *, batch_id: str, items: list[dict[str, Any]]) -> list[CommittedVersion]:
+        """暂存整批工件，最后仅写一个批次完成标记以原子公开。"""
+        if not batch_id or not items:
+            raise ValueError("批次标识和工件不能为空")
+        batch_directory = self._batch_directory(batch_id)
+        journal = batch_directory / "manifest.json"
+        if journal.exists() or (batch_directory / "_COMPLETE").exists():
+            raise ImmutableVersionError("批次标识不允许重复使用")
+        entries = []
+        for item in items:
+            dataset, version_id, content = item["dataset"], item["version_id"], item["content"]
+            if (
+                self.version_exists(dataset, version_id)
+                or (self._root / "artifacts" / dataset / version_id).exists()
+            ):
+                raise ImmutableVersionError("批次包含已存在版本")
+            entries.append(
+                {
+                    "dataset": dataset,
+                    "version_id": version_id,
+                    "parent_version_id": item.get("parent_version_id"),
+                    "content_hash": self._validate_hash(content, item.get("expected_hash")),
+                }
+            )
+        self._create_batch_directory(batch_id, entries)
+        committed: list[CommittedVersion] = []
+        try:
+            for item, entry in zip(items, entries, strict=True):
+                artifact = self._artifacts.write_artifact(
+                    entry["dataset"], entry["version_id"], item["content"], complete=False
+                )
+                self._metadata.register_batch_version(
+                    batch_id,
+                    entry["dataset"],
+                    entry["version_id"],
+                    artifact.content_hash,
+                    entry["parent_version_id"],
+                )
+                committed.append(
+                    CommittedVersion(
+                        entry["dataset"],
+                        entry["version_id"],
+                        entry["parent_version_id"],
+                        entry["content_hash"],
+                    )
+                )
+            (batch_directory / "_COMPLETE").touch()
+        except Exception:
+            try:
+                self.rollback_batch(batch_id)
+            except Exception:
+                # 日志保留给下一次服务启动恢复；不会形成可查询版本。
+                pass
+            raise
+        return committed
+
     def read_bytes(self, dataset: str, version_id: str) -> bytes:
-        """读取指定不可变版本，不隐式改为当前版本。"""
+        """只读取已经公开的版本。"""
+        if not self.version_exists(dataset, version_id):
+            raise KeyError(version_id)
         return (self._root / "artifacts" / dataset / version_id / "payload.parquet").read_bytes()
 
     def metadata_for(self, dataset: str, version_id: str) -> dict[str, str | None]:
-        """读取与不可变工件关联的 DuckDB 元数据。"""
+        """只读取已经公开版本的元数据。"""
+        if not self.version_exists(dataset, version_id):
+            raise KeyError(version_id)
         return self._metadata.get_version(dataset, version_id)
 
+    def rollback_batch(self, batch_id: str) -> None:
+        """删除未完成批次的工件和元数据；失败日志留待下次启动继续恢复。"""
+        batch_directory = self._batch_directory(batch_id)
+        versions = set(self._metadata.batch_versions(batch_id))
+        versions.update(self._journal_versions(batch_directory / "recovery.json"))
+        versions.update(self._journal_versions(batch_directory / "manifest.json"))
+        if versions:
+            self.rollback_versions(*versions)
+        self._metadata.delete_batch_versions(batch_id)
+        shutil.rmtree(batch_directory, ignore_errors=False)
+        if self._batches_root.exists() and not any(self._batches_root.iterdir()):
+            self._batches_root.rmdir()
+
     def rollback_versions(self, *versions: tuple[str, str]) -> None:
-        """删除尚未对外返回的失败批次版本及其元数据。"""
+        """删除尚未公开的失败版本及其元数据。"""
         for dataset, version_id in versions:
             self._metadata._connection.execute(
                 "DELETE FROM dataset_versions WHERE dataset = ? AND version_id = ?",
                 [dataset, version_id],
             )
             directory = self._root / "artifacts" / dataset / version_id
             if directory.exists():
-                for path in directory.iterdir():
-                    path.unlink()
-                directory.rmdir()
-                dataset_directory = directory.parent
-                if not any(dataset_directory.iterdir()):
-                    dataset_directory.rmdir()
+                shutil.rmtree(directory)
+            dataset_directory = directory.parent
+            if dataset_directory.exists() and not any(dataset_directory.iterdir()):
+                dataset_directory.rmdir()
+
+    def _recover_incomplete_batches(self) -> None:
+        """启动时幂等清理未写唯一完成标记的中断批次。"""
+        if not self._batches_root.exists():
+            return
+        for directory in list(self._batches_root.iterdir()):
+            if directory.is_dir() and (
+                not (directory / "_COMPLETE").is_file()
+                or not self._journal_is_valid(directory / "recovery.json")
+            ):
+                self.rollback_batch(directory.name)
+
+    def _completed_batch_contains(self, dataset: str, version_id: str) -> bool:
+        if not self._batches_root.exists():
+            return False
+        for directory in self._batches_root.iterdir():
+            manifest = directory / "recovery.json"
+            if (
+                not (directory / "_COMPLETE").is_file()
+                or not manifest.is_file()
+                or not self._metadata.has_version(dataset, version_id)
+            ):
+                continue
+            if not self._journal_is_valid(manifest):
+                continue
+            entries = self._journal_entries(manifest)
+            if any(
+                entry["dataset"] == dataset and entry["version_id"] == version_id
+                for entry in entries
+            ):
+                if (
+                    len(entries) == 1
+                    and not (
+                        self._root / "artifacts" / dataset / version_id / "_COMPLETE"
+                    ).is_file()
+                ):
+                    continue
+                return True
+        return False
+
+    def _batch_directory(self, batch_id: str) -> Path:
+        return self._batches_root / batch_id
+
+    def _create_batch_directory(self, batch_id: str, entries: list[dict[str, Any]]) -> Path:
+        """先原子落盘完整恢复清单，再开始写入任何工件或元数据。"""
+        batch_directory = self._batch_directory(batch_id)
+        batch_directory.mkdir(parents=True, exist_ok=False)
+        self._write_journal_atomically(batch_directory / "recovery.json", entries)
+        self._write_journal_atomically(batch_directory / "manifest.json", entries)
+        return batch_directory
+
+    @staticmethod
+    def _write_journal_atomically(journal: Path, entries: list[dict[str, Any]]) -> None:
+        temporary = journal.with_name(f".{journal.name}.{uuid.uuid4().hex}.tmp")
+        try:
+            temporary.write_text(json.dumps({"entries": entries}, sort_keys=True), encoding="utf-8")
+            temporary.replace(journal)
+        finally:
+            if temporary.exists():
+                temporary.unlink()
+
+    @classmethod
+    def _journal_is_valid(cls, manifest: Path) -> bool:
+        try:
+            cls._journal_entries(manifest)
+        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
+            return False
+        return True
+
+    @staticmethod
+    def _journal_entries(manifest: Path) -> list[dict[str, Any]]:
+        entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
+        if (
+            not entries
+            or not isinstance(entries, list)
+            or any(
+                not isinstance(entry, dict)
+                or not isinstance(entry.get("dataset"), str)
+                or not isinstance(entry.get("version_id"), str)
+                for entry in entries
+            )
+        ):
+            raise ValueError("批次日志条目无效")
+        return entries
+
+    @classmethod
+    def _journal_versions(cls, manifest: Path) -> set[tuple[str, str]]:
+        try:
+            return {
+                (entry["dataset"], entry["version_id"]) for entry in cls._journal_entries(manifest)
+            }
+        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
+            return set()
+
+    @staticmethod
+    def _validate_hash(content: bytes, expected_hash: str | None) -> str:
+        digest = hashlib.sha256(content).hexdigest()
+        if expected_hash is not None and expected_hash != digest:
+            raise ValueError("暂存工件哈希校验失败")
+        return digest
diff --git a/src/stock_agent/workers/market_ingestion.py b/src/stock_agent/workers/market_ingestion.py
index f3f8d45..ca5054a 100644
--- a/src/stock_agent/workers/market_ingestion.py
+++ b/src/stock_agent/workers/market_ingestion.py
@@ -1,19 +1,18 @@
 """通过注入读取器采集并原子保存中国市场历史日线。"""
 
 from __future__ import annotations
 
 import json
 from collections.abc import Callable
 from dataclasses import dataclass
 from datetime import datetime
-from hashlib import sha256
 from typing import Any
 from uuid import uuid4
 
 from stock_agent.application.historical_market_data import (
     HistoricalDailyBar,
     HistoricalDailyBarBatch,
     HistoricalDailyBarValidationError,
 )
 from stock_agent.application.versioning_service import VersioningService
 from stock_agent.domain.market import InstrumentIdentity, Market
@@ -70,34 +69,35 @@ class HistoricalDailyIngestionWorker:
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
-            self._versioning_service.commit_bytes(
-                dataset="market-data-raw",
-                version_id=raw_version_id,
-                content=raw_response,
-                source_id=source_id,
-                expected_hash=sha256(raw_response).hexdigest(),
-            )
-            self._versioning_service.commit_bytes(
-                dataset="market-data-normalized",
-                version_id=normalized_version_id,
-                content=normalized_content,
-                source_id=source_id,
-                parent_version_id=raw_version_id,
-                expected_hash=sha256(normalized_content).hexdigest(),
+            self._versioning_service.commit_batch(
+                batch_id=f"historical-daily-{uuid4().hex}",
+                items=[
+                    {
+                        "dataset": "market-data-raw",
+                        "version_id": raw_version_id,
+                        "content": raw_response,
+                    },
+                    {
+                        "dataset": "market-data-normalized",
+                        "version_id": normalized_version_id,
+                        "content": normalized_content,
+                        "parent_version_id": raw_version_id,
+                    },
+                ],
             )
         except HistoricalDailyIngestionError:
             self._rollback(raw_version_id, normalized_version_id)
             raise
         except Exception as error:
             self._rollback(raw_version_id, normalized_version_id)
             raise HistoricalDailyIngestionError(str(error)) from error
         return HistoricalDailyIngestionResult(bars, raw_version_id, normalized_version_id)
 
     @staticmethod
@@ -119,29 +119,38 @@ class HistoricalDailyIngestionWorker:
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
-        if (
-            payload.get("source_id") != source_id
-            or payload.get("market") != security_id.market.value
-        ):
-            raise HistoricalDailyIngestionError("历史日线来源或市场不一致")
+        expected_identity = {
+            "security_code": security_id.display_code,
+            "exchange": security_id.exchange,
+            "currency": security_id.currency,
+            "market": security_id.market.value,
+        }
+        if payload.get("source_id") != source_id:
+            raise HistoricalDailyIngestionError("历史日线来源不一致")
+        for field, expected_value in expected_identity.items():
+            if payload.get(field) != expected_value:
+                raise HistoricalDailyIngestionError(f"历史日线{field}与证券身份不一致")
         if payload.get("collected_at") != collected_at.isoformat():
             raise HistoricalDailyIngestionError("历史日线采集时间不一致")
-        if not isinstance(payload.get("data_version"), str) or not payload["data_version"]:
-            raise HistoricalDailyIngestionError("历史日线数据版本缺失")
+        if (
+            not isinstance(payload.get("source_data_version"), str)
+            or not payload["source_data_version"]
+        ):
+            raise HistoricalDailyIngestionError("历史日线上游数据版本缺失")
         return payload
 
     def _normalize_payload(
         self,
         payload: dict[str, Any],
         collected_at: datetime,
         security_id: InstrumentIdentity,
         source_id: str,
         normalized_version_id: str,
     ) -> tuple[bytes, list[IngestedHistoricalDailyBar]]:
@@ -150,71 +159,79 @@ class HistoricalDailyIngestionWorker:
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
-                    "currency": security_id.currency,
-                    "adjustment_basis": "none",
+                    "currency": payload["currency"],
+                    "adjustment_basis": payload["adjustment_basis"],
                     "source_id": source_id,
                     "collected_at": collected_at,
-                    "data_version": normalized_version_id,
+                    "source_data_version": payload["source_data_version"],
                 }
                 for bar in payload["bars"]
             ]
-            normalized = HistoricalDailyBarBatch(self._versioning_service).normalize_and_save(
-                records
-            )
+            normalized = HistoricalDailyBarBatch().normalize(records)
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
-                data_version=bar.data_version,
+                source_data_version=bar.source_data_version,
             )
             for bar in normalized
         ]
         document = {
             "source_id": source_id,
             "market": security_id.market.value,
+            "security_code": security_id.display_code,
+            "display_code": security_id.display_code,
+            "exchange": security_id.exchange,
+            "currency": security_id.currency,
             "market_time": payload["market_time"],
             "collected_at": collected_at.isoformat(),
-            "data_version": normalized_version_id,
+            "source_data_version": payload["source_data_version"],
+            "artifact_version_id": normalized_version_id,
             "bars": [
                 {
+                    "market": security_id.market.value,
+                    "security_code": security_id.display_code,
+                    "display_code": security_id.display_code,
+                    "exchange": security_id.exchange,
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
-                    "data_version": bar.data_version,
+                    "source_data_version": bar.source_data_version,
+                    "artifact_version_id": normalized_version_id,
                     "freshness": bar.freshness.state,
                 }
                 for bar in bars
             ],
         }
         return json.dumps(
             document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
         ).encode("utf-8"), bars
 
     def _rollback(self, raw_version_id: str, normalized_version_id: str) -> None:
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
index b2e3aaf..48e18a0 100644
--- a/tests/failure/test_market_data_failures.py
+++ b/tests/failure/test_market_data_failures.py
@@ -120,21 +120,21 @@ def test_新浪适配器响应缺少任一请求代码时拒绝全部行情(loca
         "market_time",
         "open",
         "high",
         "low",
         "close",
         "volume",
         "currency",
         "adjustment_basis",
         "source_id",
         "collected_at",
-        "data_version",
+        "source_data_version",
     ],
 )
 def test_标准化历史日线缺少任一契约字段时整批拒绝且不产生持久化记录(
     缺失字段: str, local_data_root: Path
 ) -> None:
     """以公开标准化日线契约校验字段，不依赖特定供应商原始响应位置。"""
 
     from stock_agent.application.historical_market_data import (
         HistoricalDailyBarBatch,
         HistoricalDailyBarValidationError,
@@ -146,28 +146,28 @@ def test_标准化历史日线缺少任一契约字段时整批拒绝且不产
         "market_time": datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
         "open": 10.0,
         "high": 10.3,
         "low": 9.9,
         "close": 10.2,
         "volume": 1000,
         "currency": "CNY",
         "adjustment_basis": "none",
         "source_id": "test-source",
         "collected_at": datetime(2026, 7, 14, 15, 1, tzinfo=UTC),
-        "data_version": "daily-v1",
+        "source_data_version": "daily-v1",
     }
     不完整日线 = 完整日线.copy()
     del 不完整日线[缺失字段]
 
-    批次 = HistoricalDailyBarBatch(VersioningService(local_data_root))
+    批次 = HistoricalDailyBarBatch()
     with pytest.raises(HistoricalDailyBarValidationError, match="缺失|完整"):
-        批次.normalize_and_save([完整日线, 不完整日线])
+        批次.normalize([完整日线, 不完整日线])
 
     assert not (local_data_root / "artifacts" / "market-data-raw").exists()
     assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
 
 
 @pytest.mark.parametrize("状态", ["DELAYED", "STALE", "CLOSED"])
 def test_当前预测拒绝过期或休市行情并给出不可用原因(状态: str) -> None:
     """当前预测入口必须把不可用原因显式反馈给调用方，不能只返回裸布尔值。"""
 
     with pytest.raises(FreshnessClassificationError, match="过期|不可用"):
@@ -242,23 +242,21 @@ def test_公司行动拒绝不合法复权比例(复权比例: float) -> None:
         )
 
 
 @pytest.mark.parametrize(
     ("action_id", "effective_at"),
     [
         ("", datetime(2026, 7, 14, 9, 0, tzinfo=UTC)),
         ("split-20260714", datetime(2026, 7, 14, 9, 0)),
     ],
 )
-def test_公司行动拒绝缺失标识或无时区日期(
-    action_id: str, effective_at: datetime
-) -> None:
+def test_公司行动拒绝缺失标识或无时区日期(action_id: str, effective_at: datetime) -> None:
     """公司行动的标识和生效时点均是可追溯复权的最小前提。"""
 
     with pytest.raises(ValueError, match="标识|时区"):
         CompanyAction(
             action_id=action_id,
             action_type="split",
             effective_at=effective_at,
             version_id="v1",
             source_id="test-source",
         )
diff --git a/tests/integration/test_sina_market_data_provenance.py b/tests/integration/test_sina_market_data_provenance.py
index db15db0..8712a73 100644
--- a/tests/integration/test_sina_market_data_provenance.py
+++ b/tests/integration/test_sina_market_data_provenance.py
@@ -45,20 +45,45 @@ def test_新浪响应和规范化结果以同一版本关联追加保存(local_d
     assert b'"market_time"' in normalized
     assert b'"collected_at"' in normalized
     assert (
         service.metadata_for("market-data-normalized", normalized_versions[0].name)[
             "parent_version_id"
         ]
         == raw_versions[0].name
     )
 
 
+def test_新浪记录器规范化工件写入失败时原始和规范化均不残留(
+    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """真实记录器必须将一对工件作为同一批次发布，失败时不得留下半批次。"""
+
+    service = VersioningService(local_data_root)
+    原写入 = service._artifacts.write_artifact
+
+    def 拒绝规范化工件(dataset: str, *参数: object, **关键字参数: object):
+        if dataset == "market-data-normalized":
+            raise OSError("规范化工件写入失败")
+        return 原写入(dataset, *参数, **关键字参数)
+
+    monkeypatch.setattr(service._artifacts, "write_artifact", 拒绝规范化工件)
+
+    with pytest.raises(OSError, match="规范化工件写入失败"):
+        SinaMarketDataFactRecorder(service).record(新浪响应(), b'{"quotes":[]}')
+
+    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
+    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
+    assert service._metadata._connection.execute(
+        "SELECT COUNT(*) FROM dataset_versions"
+    ).fetchone() == (0,)
+
+
 def test_新浪事实保存失败时不返回未持久化行情(local_data_root: Path) -> None:
     """事实链提交失败必须使整批读取失败，不能把内存结果冒充事实。"""
 
     class 失败记录器:
         def record(self, raw_response: bytes, quotes: list[object]) -> None:
             raise RuntimeError("本地保存失败")
 
     adapter = SinaHttpAdapter(
         lambda _url: 新浪响应(),
         fact_recorder=失败记录器(),
diff --git a/tests/integration/test_single_market_daily_pipeline.py b/tests/integration/test_single_market_daily_pipeline.py
index 9fa3c66..f47c008 100644
--- a/tests/integration/test_single_market_daily_pipeline.py
+++ b/tests/integration/test_single_market_daily_pipeline.py
@@ -23,25 +23,29 @@ def 固定历史日线响应() -> bytes:
                 {
                     "close": 10.20,
                     "high": 10.50,
                     "low": 9.80,
                     "open": 10.00,
                     "trade_date": "2026-07-13",
                     "volume": 1_000_000,
                 }
             ],
             "collected_at": "2026-07-14T07:01:02+00:00",
-            "data_version": "sina-固定历史响应-1",
+            "source_data_version": "sina-固定历史响应-1",
+            "adjustment_basis": "none",
+            "currency": "CNY",
+            "exchange": "SSE",
             "market": "CN",
             "market_time": "2026-07-13T15:00:00+08:00",
             "response_schema_version": "固定历史日线响应-1",
             "source_id": "sina",
+            "security_code": "600000",
         },
         ensure_ascii=False,
         separators=(",", ":"),
         sort_keys=True,
     ).encode("utf-8")
 
 
 def 创建工作者(读取历史日线, 服务: VersioningService):
     """延迟导入尚未实现的工作者，使红灯直接指向 US1 的生产缺口。"""
 
@@ -93,58 +97,63 @@ def test_历史日线将注入响应追加保存为原始与规范化工件并
     assert 结果.bars[0].source_id == "sina"
     assert 结果.bars[0].freshness.state != "REALTIME"
     原始工件 = 服务.read_bytes("market-data-raw", 结果.raw_version_id)
     原始批次 = json.loads(原始工件)
     原始元数据 = 服务.metadata_for("market-data-raw", 结果.raw_version_id)
     assert 原始工件 == 原始响应
     assert 原始批次["source_id"] == "sina"
     assert 原始批次["market"] == "CN"
     assert 原始批次["market_time"] == "2026-07-13T15:00:00+08:00"
     assert 原始批次["collected_at"] == "2026-07-14T07:01:02+00:00"
-    assert 原始批次["data_version"] == "sina-固定历史响应-1"
+    assert 原始批次["source_data_version"] == "sina-固定历史响应-1"
     assert 原始元数据["content_hash"] == hashlib.sha256(原始工件).hexdigest()
     assert 原始元数据["parent_version_id"] is None
 
     规范化工件 = 服务.read_bytes("market-data-normalized", 结果.normalized_version_id)
     规范化批次 = json.loads(规范化工件)
     元数据 = 服务.metadata_for("market-data-normalized", 结果.normalized_version_id)
     assert 规范化批次["source_id"] == "sina"
     assert 规范化批次["market"] == "CN"
     assert 规范化批次["collected_at"] == "2026-07-14T07:01:02+00:00"
     assert 规范化批次["bars"][0]["market_time"] == "2026-07-13T15:00:00+08:00"
-    assert 规范化批次["bars"][0]["data_version"] == 结果.normalized_version_id
-    assert 规范化批次["data_version"] == 结果.normalized_version_id
+    assert 规范化批次["bars"][0]["source_data_version"] == "sina-固定历史响应-1"
+    assert 规范化批次["bars"][0]["adjustment_basis"] == "none"
+    assert 规范化批次["bars"][0]["artifact_version_id"] == 结果.normalized_version_id
+    assert 规范化批次["security_code"] == "600000"
+    assert 规范化批次["display_code"] == "600000"
+    assert 规范化批次["exchange"] == "SSE"
+    assert 规范化批次["currency"] == "CNY"
+    assert 规范化批次["bars"][0]["security_code"] == "600000"
+    assert 规范化批次["bars"][0]["exchange"] == "SSE"
+    assert 规范化批次["source_data_version"] == "sina-固定历史响应-1"
+    assert 规范化批次["artifact_version_id"] == 结果.normalized_version_id
     assert 元数据["parent_version_id"] == 结果.raw_version_id
     assert 元数据["content_hash"] == hashlib.sha256(规范化工件).hexdigest()
 
 
 def test_相同历史响应重采集会追加可追溯新记录而非静默覆盖(
     local_data_root: Path,
 ) -> None:
     """相同内容的再次采集必须产生新的原始和规范化版本，并保留各自父链。"""
 
     服务 = VersioningService(local_data_root)
     工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)
 
     首次 = 工作者.collect_and_save(**采集参数())
     第二次 = 工作者.collect_and_save(**采集参数())
 
     assert 首次.raw_version_id != 第二次.raw_version_id
     assert 首次.normalized_version_id != 第二次.normalized_version_id
     assert 服务.read_bytes("market-data-raw", 首次.raw_version_id) == 固定历史日线响应()
+    assert 服务.read_bytes("market-data-raw", 第二次.raw_version_id) == 固定历史日线响应()
     assert (
-        服务.read_bytes("market-data-raw", 第二次.raw_version_id) == 固定历史日线响应()
-    )
-    assert (
-        服务.metadata_for("market-data-normalized", 首次.normalized_version_id)[
-            "parent_version_id"
-        ]
+        服务.metadata_for("market-data-normalized", 首次.normalized_version_id)["parent_version_id"]
         == 首次.raw_version_id
     )
     assert (
         服务.metadata_for("market-data-normalized", 第二次.normalized_version_id)[
             "parent_version_id"
         ]
         == 第二次.raw_version_id
     )
 
 
@@ -173,28 +182,28 @@ def test_任一日线字段非法时原始与规范化两侧均不留下半批
 
 @pytest.mark.parametrize("失败数据集", ["market-data-raw", "market-data-normalized"])
 def test_任一工件保存失败时历史日线原子回滚且报告失败原因(
     失败数据集: str, local_data_root: Path, monkeypatch: pytest.MonkeyPatch
 ) -> None:
     """两侧工件必须作为一个批次提交；任一保存失败均不可留下可见版本。"""
 
     from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError
 
     服务 = VersioningService(local_data_root)
-    原提交 = 服务.commit_bytes
+    原提交 = 服务.commit_batch
 
-    def 失败提交(*, dataset: str, **参数: object):
-        if dataset == 失败数据集:
+    def 失败提交(*, items: list[dict[str, object]], **参数: object):
+        if any(item["dataset"] == 失败数据集 for item in items):
             raise OSError(f"{失败数据集} 保存失败")
-        return 原提交(dataset=dataset, **参数)
+        return 原提交(items=items, **参数)
 
-    monkeypatch.setattr(服务, "commit_bytes", 失败提交)
+    monkeypatch.setattr(服务, "commit_batch", 失败提交)
     工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)
 
     with pytest.raises(HistoricalDailyIngestionError, match="保存失败"):
         工作者.collect_and_save(**采集参数())
 
     断言不存在半批工件或元数据(服务, local_data_root)
 
 
 @pytest.mark.parametrize("失败数据集", ["market-data-raw", "market-data-normalized"])
 @pytest.mark.parametrize("失败时点", ["元数据登记", "完成标记"])
@@ -230,37 +239,88 @@ def test_工件字节写入后元数据登记或完成标记失败时两侧零
             (目录 / "manifest.json").write_text(
                 json.dumps({"content_hash": hashlib.sha256(content).hexdigest()}),
                 encoding="utf-8",
             )
             raise OSError(f"{失败数据集} 完成标记失败")
 
         monkeypatch.setattr(服务._artifacts, "write_artifact", 完成标记前失败)
 
     工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)
 
-    with pytest.raises(
-        HistoricalDailyIngestionError, match="元数据登记失败|完成标记失败"
-    ):
+    with pytest.raises(HistoricalDailyIngestionError, match="元数据登记失败|完成标记失败"):
         工作者.collect_and_save(**采集参数())
 
     断言不存在半批工件或元数据(服务, local_data_root)
 
 
 def test_历史日线不得作为当前预测的实时输入(local_data_root: Path) -> None:
     """闭环产物只能用于历史研究；即使日线完整也必须被当前预测入口拒绝。"""
 
     服务 = VersioningService(local_data_root)
-    结果 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务).collect_and_save(
-        **采集参数()
-    )
-
+    结果 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务).collect_and_save(**采集参数())
     assert (
         is_usable_for_current_prediction(
             {
                 "collected_at": 结果.bars[0].collected_at,
                 "market_time": 结果.bars[0].market_time,
                 "state": "CLOSED",
                 "time_is_verifiable": True,
             }
         )
         is False
     )
+
+
+@pytest.mark.parametrize(
+    ("字段", "错误值"),
+    [
+        ("security_code", "000001"),
+        ("exchange", "SZSE"),
+        ("currency", "USD"),
+        ("market", "US"),
+    ],
+)
+def test_payload_证券身份任一字段与调用身份不一致时整批拒绝且零残留(
+    字段: str, 错误值: str, local_data_root: Path
+) -> None:
+    """供应商载荷必须显式复核证券代码、交易所、币种和市场。"""
+
+    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError
+
+    payload = json.loads(固定历史日线响应())
+    payload[字段] = 错误值
+    服务 = VersioningService(local_data_root)
+    工作者 = 创建工作者(
+        lambda **_参数: json.dumps(payload, ensure_ascii=False).encode("utf-8"), 服务
+    )
+
+    with pytest.raises(HistoricalDailyIngestionError, match="证券|市场|交易所|币种"):
+        工作者.collect_and_save(**采集参数())
+
+    断言不存在半批工件或元数据(服务, local_data_root)
+
+
+def test_批次完成标记失败时两侧均不可查询且下次启动会恢复(
+    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """唯一批次完成标记失败不能把任一侧暴露为独立版本。"""
+
+    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError
+
+    服务 = VersioningService(local_data_root)
+    原触碰 = Path.touch
+
+    def 拒绝批次完成标记(path: Path, *参数: object, **关键字参数: object) -> None:
+        if path.name == "_COMPLETE" and ".batches" in path.parts:
+            raise OSError("批次完成标记失败")
+        原触碰(path, *参数, **关键字参数)
+
+    monkeypatch.setattr(Path, "touch", 拒绝批次完成标记)
+    with pytest.raises(HistoricalDailyIngestionError, match="批次完成标记失败"):
+        创建工作者(lambda **_参数: 固定历史日线响应(), 服务).collect_and_save(**采集参数())
+
+    assert list((local_data_root / "artifacts").rglob("_COMPLETE")) == []
+    assert 服务._metadata._connection.execute(
+        "SELECT COUNT(*) FROM dataset_versions"
+    ).fetchone() == (0,)
+    恢复后服务 = VersioningService(local_data_root)
+    断言不存在半批工件或元数据(恢复后服务, local_data_root)
diff --git a/tests/integration/test_versioning_atomic_commit.py b/tests/integration/test_versioning_atomic_commit.py
new file mode 100644
index 0000000..fd5f646
--- /dev/null
+++ b/tests/integration/test_versioning_atomic_commit.py
@@ -0,0 +1,206 @@
+"""验证原始行情与预测快照只能追加写入，失败暂存不会污染已验证版本。"""
+
+from pathlib import Path
+
+import pytest
+
+
+def test_版本提交保留父版本且拒绝静默覆盖(local_data_root: Path) -> None:
+    """同一版本标识不能覆盖既有事实，修订必须显式引用父版本。"""
+
+    from stock_agent.application.versioning_service import ImmutableVersionError, VersioningService
+
+    service = VersioningService(local_data_root)
+    original = service.commit_bytes(
+        dataset="daily-bars",
+        version_id="v1",
+        content=b"first",
+        source_id="test-source",
+    )
+    revised = service.commit_bytes(
+        dataset="daily-bars",
+        version_id="v2",
+        content=b"revised",
+        source_id="test-source",
+        parent_version_id="v1",
+        revision_reason="修订来源字段",
+    )
+
+    assert original.parent_version_id is None
+    assert revised.parent_version_id == "v1"
+    assert service.read_bytes("daily-bars", "v1") == b"first"
+
+    with pytest.raises(ImmutableVersionError):
+        service.commit_bytes(
+            dataset="daily-bars", version_id="v1", content=b"overwrite", source_id="test-source"
+        )
+
+
+def test_暂存校验失败不产生可见版本(local_data_root: Path) -> None:
+    """不完整暂存工件不能被登记为已提交版本。"""
+
+    from stock_agent.application.versioning_service import VersioningService
+
+    service = VersioningService(local_data_root)
+
+    with pytest.raises(ValueError, match="哈希"):
+        service.commit_bytes(
+            dataset="daily-bars",
+            version_id="v1",
+            content=b"payload",
+            source_id="test-source",
+            expected_hash="0" * 64,
+        )
+
+    assert not service.version_exists("daily-bars", "v1")
+
+
+def test_提交版本必须登记元数据并写入完成标记(local_data_root: Path) -> None:
+    """版本链只有在工件完成与 DuckDB 元数据同时存在时才可供查询。"""
+
+    from stock_agent.application.versioning_service import VersioningService
+
+    service = VersioningService(local_data_root)
+    committed = service.commit_bytes(
+        dataset="daily-bars", version_id="v1", content=b"payload", source_id="test-source"
+    )
+
+    assert (local_data_root / "artifacts" / "daily-bars" / "v1" / "_COMPLETE").is_file()
+    assert service.metadata_for("daily-bars", "v1")["content_hash"] == committed.content_hash
+
+
+@pytest.mark.parametrize("损坏内容", ['{"entries":[', "{}"])
+def test_启动恢复损坏批次日志时清理元数据和双方工件(local_data_root: Path, 损坏内容: str) -> None:
+    """截断日志不得阻断初始化，已登记的未完成批次必须被安全清理。"""
+
+    from stock_agent.application.versioning_service import VersioningService
+
+    service = VersioningService(local_data_root)
+    batch_id = "损坏日志批次"
+    batch_directory = local_data_root / ".batches" / batch_id
+    batch_directory.mkdir(parents=True)
+    batch_directory.joinpath("manifest.json").write_text(损坏内容, encoding="utf-8")
+    for dataset, version_id in (
+        ("market-data-raw", "raw-1"),
+        ("market-data-normalized", "normalized-1"),
+    ):
+        artifact = service._artifacts.write_artifact(
+            dataset, version_id, b"payload", complete=False
+        )
+        service._metadata.register_batch_version(
+            batch_id, dataset, version_id, artifact.content_hash, None
+        )
+
+    recovered = VersioningService(local_data_root)
+
+    assert not batch_directory.exists()
+    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
+    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
+    assert recovered._metadata._connection.execute(
+        "SELECT COUNT(*) FROM dataset_versions"
+    ).fetchone() == (0,)
+
+
+def test_single_commit_marker_failure_is_invisible_and_recovered(
+    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """元数据已登记但完成标记未公开时不得读取半提交。"""
+    from stock_agent.application.versioning_service import VersioningService
+
+    service = VersioningService(local_data_root)
+    original_touch = Path.touch
+
+    def reject_single_complete_marker(path: Path, *args: object, **kwargs: object) -> None:
+        if path.name == "_COMPLETE" and ".batches" not in path.parts:
+            raise OSError("单工件完成标记失败")
+        original_touch(path, *args, **kwargs)
+
+    monkeypatch.setattr(Path, "touch", reject_single_complete_marker)
+    with pytest.raises(OSError, match="完成标记"):
+        service.commit_bytes(
+            dataset="daily-bars", version_id="v1", content=b"payload", source_id="test-source"
+        )
+
+    assert not service.version_exists("daily-bars", "v1")
+    with pytest.raises(KeyError):
+        service.read_bytes("daily-bars", "v1")
+    with pytest.raises(KeyError):
+        service.metadata_for("daily-bars", "v1")
+
+    recovered = VersioningService(local_data_root)
+    assert not (local_data_root / "artifacts" / "daily-bars").exists()
+    assert recovered._metadata._connection.execute(
+        "SELECT COUNT(*) FROM dataset_versions"
+    ).fetchone() == (0,)
+
+
+def test_interrupted_single_commit_is_recovered_on_next_startup(
+    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """进程在补偿前中断时，下一次启动仍能从暂存目录清理全部残留。"""
+    from stock_agent.application.versioning_service import VersioningService
+
+    service = VersioningService(local_data_root)
+    original_touch = Path.touch
+
+    def reject_single_complete_marker(path: Path, *args: object, **kwargs: object) -> None:
+        if path.name == "_COMPLETE" and ".batches" not in path.parts:
+            raise OSError("单工件完成标记失败")
+        original_touch(path, *args, **kwargs)
+
+    monkeypatch.setattr(Path, "touch", reject_single_complete_marker)
+
+    def reject_rollback(_batch_id: str) -> None:
+        raise OSError("进程中断")
+
+    monkeypatch.setattr(service, "rollback_batch", reject_rollback)
+    with pytest.raises(OSError, match="完成标记"):
+        service.commit_bytes(
+            dataset="daily-bars", version_id="v1", content=b"payload", source_id="test-source"
+        )
+
+    assert not service.version_exists("daily-bars", "v1")
+    recovered = VersioningService(local_data_root)
+    assert not (local_data_root / "artifacts" / "daily-bars").exists()
+    assert recovered._metadata._connection.execute(
+        "SELECT COUNT(*) FROM dataset_versions"
+    ).fetchone() == (0,)
+
+
+@pytest.mark.parametrize("damaged_journal", ["{}", '{"entries":['])
+def test_damaged_or_empty_journal_without_batch_index_uses_staging_manifest_for_recovery(
+    local_data_root: Path, damaged_journal: str
+) -> None:
+    """恢复以暂存目录中的原子清单为准，不能依赖已登记批次索引。"""
+    import json
+
+    from stock_agent.application.versioning_service import VersioningService
+
+    service = VersioningService(local_data_root)
+    batch_directory = local_data_root / ".batches" / "无索引损坏批次"
+    batch_directory.mkdir(parents=True)
+    entries = [
+        {"dataset": "market-data-raw", "version_id": "raw-1", "parent_version_id": None},
+        {
+            "dataset": "market-data-normalized",
+            "version_id": "normalized-1",
+            "parent_version_id": "raw-1",
+        },
+    ]
+    batch_directory.joinpath("recovery.json").write_text(
+        json.dumps({"entries": entries}), encoding="utf-8"
+    )
+    batch_directory.joinpath("manifest.json").write_text(damaged_journal, encoding="utf-8")
+    for entry in entries:
+        service._artifacts.write_artifact(
+            entry["dataset"], entry["version_id"], b"payload", complete=False
+        )
+
+    recovered = VersioningService(local_data_root)
+
+    assert not batch_directory.exists()
+    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
+    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
+    assert recovered._metadata._connection.execute(
+        "SELECT COUNT(*) FROM dataset_versions"
+    ).fetchone() == (0,)

```

