# T040 独立审查问题修复报告

## 修复结果

- `VersioningService.commit_batch()` 为原始和规范化工件建立同一批次日志；两侧先写入无 `_COMPLETE` 的暂存工件并登记元数据，最后只在 `.batches/<batch_id>/_COMPLETE` 写入单一完成标记。
- `version_exists()`、`read_bytes()` 与 `metadata_for()` 仅将单版本完成工件或含单一批次完成标记的批次成员视为可见。批次中断、完成标记失败或补偿失败均不会让任一侧独立可查询。
- 服务初始化会扫描未完成批次日志，幂等删除工件目录和 DuckDB 元数据，作为进程中断或补偿失败后的恢复策略。
- 标准化接口改为准确的 `HistoricalDailyBarBatch.normalize()`，仅执行全批校验和标准化；持久化只能由受控的 `HistoricalDailyIngestionWorker` 完成。
- 规范化产物保留 `source_data_version`、`adjustment_basis` 和本地 `artifact_version_id`，不再使用本地 UUID 覆盖上游来源版本。
- 载荷必须显式携带并匹配 `security_code`、`exchange`、`currency`、`market`；任一不匹配会整批拒绝且不留可见工件或元数据。

## TDD 红灯与绿灯

先新增并运行以下回归测试，红灯分别证明旧实现缺少来源版本保留、未核验代码/交易所/币种，以及存在两侧独立完成标记：

- 批次唯一完成标记失败时两侧均不可查询，并在下次启动恢复。
- 上游证券代码、交易所、币种、市场任一不匹配时整批拒绝。
- 规范化工件同时保存上游版本、复权口径和本地产物版本。

实现后，以下相关组合测试通过：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py -v
```

结果：`27 passed`。

按任务指定组合运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -q
```

结果：`52 passed, 14 failed`。14 项均为本任务范围外的既有缺口：当前预测新鲜度拒绝、跨市场证券身份校验、代码歧义解析、公司行动与复权规则；未涉及本次批次提交路径。

## 质量检查

```powershell
py -3.12 -m ruff format --check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py src/stock_agent/adapters/storage/parquet_store.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py
py -3.12 -m ruff check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py src/stock_agent/adapters/storage/parquet_store.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py
py -3.12 tools/check_chinese_project_text.py
```

三项检查均通过。

全量命令 `py -3.12 -m pytest -o addopts='' -q` 在收集阶段被既有缺失模块阻断：

- `stock_agent.desktop.pages.market_page`
- `stock_agent.application.market_service`

因此未能进入完整测试执行；该阻断与本次修改无关。

## 风险与恢复边界

批次完成标记写入前，即使原始或规范化目录、元数据已经存在，也不会被本服务的查询接口视为可见版本；启动恢复会清除未完成批次。单一完成标记写入后两侧同时公开。当前实现依赖所有调用方通过 `VersioningService` 查询，不应绕过服务直接枚举 `artifacts` 目录并将无完成标记目录当作有效版本。
