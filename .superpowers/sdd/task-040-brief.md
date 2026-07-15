# T040：一市场历史日线采集、原子保存与标准化工作者

## 目标

实现 T037 的历史日线闭环红灯：固定注入响应 -> 原始工件 -> 规范化日线 -> 原子可回读本地事实链。

## 修改范围

- 新建：`src/stock_agent/workers/market_ingestion.py`
- 可修改：为满足 T036/T037 已批准公开契约所需的最小领域或存储文件。
- 修改：相关集成/失败测试，只能用于接入真实公开接口；不得删除任何已批准断言。

## 行为要求

1. 只接收注入的历史日线读取器与同一 `VersioningService`，不自行发网络请求；来源必须明确为 `sina`，市场为 `CN`，并保留来源、市场时间、采集时间、数据版本与内容哈希。
2. 历史日线标准化契约必须验证证券身份、交易日、开高低收、成交量、复权口径、币种、来源、市场时间、采集时间和版本；历史日线不得标为实时。
3. 每次成功采集追加保存原始与规范化工件，使用来源/时点/版本/哈希与父版本建立可回读关联；重采集相同内容仍形成可追溯新采集记录，绝不静默覆盖。
4. 任一字段/规范化/保存失败都必须回滚 raw 与 normalized 工件、元数据和完成标记，保留结构化失败原因；禁止部分成功。
5. 实现 T036 所需的 `HistoricalDailyBarBatch` 最小公开接口，字段缺失/空值时全批拒绝、双侧零残留。

## TDD 与验证

T037 已记录 11 个红灯，先运行：

`py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v`

确认失败源于缺少 worker/interface，再最小实现并运行至通过。随后运行全量 pytest、Ruff 格式/检查和中文规范检查。报告写入 `D:/personal/bagholder/.superpowers/sdd/task-040-report.md`，含红绿证据、回滚策略与命令结果。提交后只回复提交、测试摘要、concerns。
