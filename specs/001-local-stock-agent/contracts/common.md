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

市场时间、采集时间、来源和数据版本是量化结果必填字段。所有时间保留带时区市场时间与 UTC。
`STALE` 数据不得驱动当前预测；`CLOSED` 显示最近有效行情但不标为实时。
