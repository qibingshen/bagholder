# T040 最终审查原子性修复报告

## 修复结果

- 单工件 `commit_bytes()` 现在先建立带完整恢复清单的暂存批次，写入未完成工件并登记元数据，最后依次公开工件完成标记与批次完成标记。查询接口同时校验完成证据和元数据，因此任一中断阶段均不会读取半提交。
- 每个暂存批次在写入工件前原子落盘 `recovery.json`；恢复以该清单为权威。空条目 journal 被拒绝，截断、损坏或空 journal 即使发生在 `batch_versions` 尚未登记时，也会清理工件目录、`dataset_versions` 和 `batch_versions`，且不会阻断启动。
- 历史 normalized 载荷及其每条 bar 均保留完整证券身份：`market`、`security_code`、`display_code`、`exchange`、`currency`。原始与规范化工件仍通过 `commit_batch()` 成对提交。

## TDD 证据

先新增并确认以下测试红灯：

- 单工件完成标记失败后，旧实现会遗留数据集目录；
- 损坏或空 journal 且批次索引未登记时，旧实现无法根据暂存目录清理工件；
- normalized 载荷回读时，旧实现缺少 `security_code` 等完整身份字段。

实现后相关回归转绿：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py tests/integration/test_single_market_daily_pipeline.py tests/integration/test_sina_market_data_provenance.py -q
```

结果：`34 passed`。

## 质量检查

```powershell
py -3.12 -m ruff format --check src/stock_agent/application/versioning_service.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/workers/market_ingestion.py tests/integration/test_versioning_atomic_commit.py tests/integration/test_single_market_daily_pipeline.py
py -3.12 -m ruff check src/stock_agent/application/versioning_service.py src/stock_agent/adapters/storage/duckdb_store.py src/stock_agent/workers/market_ingestion.py tests/integration/test_versioning_atomic_commit.py tests/integration/test_single_market_daily_pipeline.py
py -3.12 tools/check_chinese_project_text.py
```

三项检查均通过。

## 全量测试阻断

全量命令 `py -3.12 -m pytest -o addopts='' -q` 在收集阶段被既有缺失模块阻断，尚未执行到测试主体：

- `stock_agent.desktop.pages.market_page`
- `stock_agent.application.market_service`

本次未引入真实网络请求或交易行为。
