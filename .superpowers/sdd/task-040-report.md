# T040 一市场历史日线采集、原子保存与标准化工作者报告

## 实现范围

- 新增 `HistoricalDailyIngestionWorker`：只调用构造时注入的历史日线读取器，不含 HTTP 或其他网络调用。
- 仅接受 `sina` 与 `CN` 证券身份；保存原始响应与标准化日线，保留来源、市场时间、采集时间、数据版本、内容哈希及父版本关系。
- 新增 `HistoricalDailyBarBatch` 最小公开接口，任一契约字段缺失、空值或价格区间无效时整批拒绝。
- 同内容重采集使用新的 UUID 版本标识，保留新的原始工件和对应标准化父链，不覆盖旧版本。

## 红灯证据

命令：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
```

首次结果：61 项中 37 项失败、24 项通过。目标集成测试的失败原因是
`ModuleNotFoundError: No module named 'stock_agent.workers.market_ingestion'`，符合 T037 记录的缺失 worker/interface 红灯。

## 绿灯证据

同一命令在实现后结果为 47 项通过、14 项失败。与 T040 有关的 11 个
`test_single_market_daily_pipeline.py` 用例和 12 个
`HistoricalDailyBarBatch` 缺字段拒绝用例均通过。剩余 14 项失败属于尚未实现的当前预测新鲜度显式拒绝、跨市场证券身份、公司行为/复权规则，不由本任务改动。

## 回滚策略

工作者在任何读取、解析、标准化或两侧保存失败时，调用同一
`VersioningService.rollback_versions` 删除本批次已写入的原始与标准化目录、完成标记和 DuckDB 元数据。版本标识在保存前生成，因此即使字节写入、元数据登记或完成标记中途失败，也会清理两侧残留；未对外返回任何部分结果。

## 其他命令结果

```powershell
py -3.12 -m ruff format --check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py
py -3.12 -m ruff check src/stock_agent/application/historical_market_data.py src/stock_agent/application/versioning_service.py src/stock_agent/workers/market_ingestion.py
py -3.12 tools/check_chinese_project_text.py
```

以上检查通过。

全量 `py -3.12 -m pytest -o addopts='' -v` 在收集阶段因既有缺失模块
`stock_agent.desktop.pages.market_page` 与
`stock_agent.application.market_service` 报 2 个错误，未进入 T040 测试执行。

全仓 Ruff 同时报告既有测试及工具文件的格式/导入/行长问题；T040 修改文件的格式与检查均通过。
