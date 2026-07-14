# T037 报告：一市场历史日线本地闭环集成测试

## 任务边界

本任务只新增集成红灯测试和数据源选择验收说明，未新增或修改生产代码，未发起真实网络请求，未接入券商、
下单或交易能力。

## 已新增的验收约束

- 首个 US1 历史日线闭环仅登记 `sina` A 股公开只读能力，并写明精确 URL
  `http://hq.sinajs.cn/list={sh|sz 加六位代码的逗号分隔列表}` 的能力边界。
- 明确新浪不构成已授权实时源，也不因该公开报价 URL 而被视为已承诺历史日线、复权或公司行动。
- 固定响应通过依赖注入传给待实现的历史日线工作者；测试中没有 HTTP 客户端或真实网络调用。
- 要求原始响应与规范化日线追加保存，可按来源、市场时间、采集时间、版本、内容哈希和父版本回读关联。
- 要求相同内容重采集保留新记录；字段非法、原始保存失败或规范化保存失败时两侧原子回滚。
- 要求历史日线不能标记为实时，也不能作为当前预测的实时输入。

## 审查修正

- 历史日线预测降级断言改为 `is_usable_for_current_prediction(...) is False`；与 T041 既有契约一致，
仅时点字段自身无效时才由领域层抛出时间异常。
- 成功路径同时回读原始与规范化工件，逐项校验来源、市场、市场时间、采集时间、数据版本、内容哈希、
元数据和父版本关联。
- 增加工件字节已写入后元数据登记失败、以及完成标记前失败的注入场景；两种失败均要求原始和规范化
工件目录、完成标记及元数据登记零残留。

## 红灯验证

执行时间：2026-07-14

```text
py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py -v
```

结果：收集 7 个测试，7 个失败，退出码 `1`。

关键输出：

```text
ModuleNotFoundError: No module named 'stock_agent.workers.market_ingestion'
============================== 7 failed in 1.59s ==============================
```

失败原因符合预期：T040 规定的历史日线采集、原始响应保存和标准化工作者尚未实现。失败发生在导入生产
缺口处，早于任何网络行为；因此当前测试是有效红灯，而不是用测试替代生产实现。

## 后续实现者接口契约

测试要求在 `stock_agent.workers.market_ingestion` 中提供：

- `HistoricalDailyIngestionWorker(read_historical_daily, versioning_service)`；
- `collect_and_save(security_id, source_id, collected_at)`；
- `HistoricalDailyIngestionError`；
- 返回具有 `bars`、`raw_version_id` 和 `normalized_version_id` 的结果。

实现必须保持读取函数可注入，并在原始与规范化工件之间提供可回读的父版本关联和真正的原子回滚。生产
实现完成后，应重新运行上述命令，预期所有红灯转绿；本任务没有执行生产实现或绿灯验证。

## 审查修正后的红灯验证

执行时间：2026-07-14

```text
py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py -v
```

结果：收集 11 个测试，11 个失败，退出码 `1`。

关键输出：

```text
ModuleNotFoundError: No module named 'stock_agent.workers.market_ingestion'
============================= 11 failed in 0.94s ==============================
```

红灯仍准确指向尚未实现的 T040 历史日线工作者。新增的元数据登记和完成标记前故障注入均使用本地
版本服务与固定响应，不包含真实网络行为。
