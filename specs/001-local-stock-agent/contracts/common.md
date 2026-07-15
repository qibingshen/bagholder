# 通用契约

所有桌面、本地服务、工作者、训练与 MCP 的成功结果使用同一信封：

```json
{
  "contract_version": "1.0",
  "result_id": "uuid",
  "request_id": "uuid",
  "generated_at": "UTC 时间",
  "data_as_of": "市场时间",
  "data_version": "dataset_version_id",
  "freshness": {"state": "REALTIME|NEAR_REALTIME|DELAYED|STALE|CLOSED", "age_seconds": 0},
  "provenance": [{"source_id": "", "collected_at": "", "artifact_hash": ""}],
  "warnings": [],
  "payload": {}
}
```

错误使用 `{code, message_zh, retryable, correlation_id, safe_recovery_action}`。不得包含凭据、
令牌、原始授权头或内部堆栈。所有请求携带调用方和 `contract_version`；写任务另携带 `task_id`。

## 分页、超时与资源边界

所有可能返回集合的查询必须使用稳定排序，并接受 `page_size`（1–200，默认 50）与不透明的
`page_cursor`。响应在 `payload.page` 中返回 `{next_cursor, returned_count, total_is_estimate}`；
游标必须绑定调用方、查询摘要、数据版本和 10 分钟有效期，参数不一致、过期或篡改时返回
`INVALID_PAGE_CURSOR`，不得回退为无界查询。

每个请求必须携带或使用服务端默认 `timeout_ms`。默认查询超时为 5,000 ms，历史或报告的
分页查询上限为 15,000 ms，非破坏性分析任务启动上限为 30,000 ms；客户端请求不得提高这些
上限。超过上限返回 `TIMEOUT`，其中包含已安全产生的 `partial_result_id`（如有）、
`safe_recovery_action` 和 `retryable`，但不得把部分结果伪装成完整量化结论。

服务端必须限制单请求最多 200 条记录、最多 10,000 根 K 线、最多 64 MiB 序列化响应和最多
一个非破坏性分析任务。超过限制分别返回 `RESOURCE_LIMIT_EXCEEDED` 或 `TASK_ALREADY_ACTIVE`，
并记录脱敏审计事件。写任务和可重试的非破坏性任务必须使用调用方提供的 `idempotency_key`；
同一键在 24 小时内仅复用同一任务或同一结果，不得重复执行。

任何契约演进必须提高 `contract_version` 的次版本号或主版本号，并在响应中回显实际版本。
同一主版本只允许新增可选字段；删除、改名或改变既有字段语义必须发布新主版本。客户端请求
不受支持的版本时返回 `CONTRACT_VERSION_UNSUPPORTED`，且不执行任务。

市场时间、采集时间、来源和数据版本是量化结果必填字段。所有时间保留带时区市场时间与 UTC。
`STALE` 数据不得驱动当前预测；`CLOSED` 显示最近有效行情但不标为实时。
