# T040 原子发布第二轮修复报告

## 修复结果

- `SinaMarketDataFactRecorder` 已改为一次调用 `VersioningService.commit_batch()` 发布原始响应与规范化事实；任一工件写入失败时，批次回滚原始工件、规范化工件和两者元数据，不产生单侧 `_COMPLETE`。
- 批次 journal 先写入同目录临时文件，再以替换操作发布 `manifest.json`，避免直接覆盖留下截断内容。
- DuckDB 增加批次成员恢复索引。启动恢复将 JSON 截断、缺少 `entries` 或条目结构无效的 journal 都视为未完成批次，以恢复索引和可解析日志的并集清理工件与元数据，不让 JSON 解析异常阻断初始化。
- 未改变历史日线 worker 的 `commit_batch()` 使用方式、来源时点字段或版本语义；测试全程没有真实网络或交易。

## TDD 证据

- 先新增真实 Sina 记录器的规范化工件写入失败回归：旧实现失败后仍保留 `market-data-raw`。
- 先新增损坏 journal 恢复回归：旧实现缺少批次恢复索引；补充 `{}` 合法但结构损坏场景后，旧实现因 `KeyError: 'entries'` 阻断初始化。
- 最小实现后，两类回归均转绿。

## 验证结果

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -q
```

结果：`65 passed, 14 failed`。14 项均为既有且不属于本次批次发布路径的市场规则、当前预测新鲜度和公司行动缺口。

```powershell
py -3.12 -m pytest -o addopts='' -q
```

全量在收集阶段被既有缺失模块阻断：`stock_agent.desktop.pages.market_page` 与 `stock_agent.application.market_service`。

```powershell
py -3.12 -m ruff format --check src/stock_agent/adapters/market_data/sina_provenance.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/application/versioning_service.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_versioning_atomic_commit.py
py -3.12 -m ruff check src/stock_agent/adapters/market_data/sina_provenance.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/application/versioning_service.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_versioning_atomic_commit.py
py -3.12 tools/check_chinese_project_text.py
```

三项检查通过。

## 风险边界

- 批次完成标记写入前，版本服务不会把任一成员视为可见；启动恢复会清理未完成或日志无效的批次。
- 损坏日志恢复依赖批次成员恢复索引；该索引在每个成员的元数据登记时写入，覆盖已登记的双侧残留。
