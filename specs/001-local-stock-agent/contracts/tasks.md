# 任务契约

任务字段：`task_id`、类型、去重键、触发源、输入版本/参数、状态、尝试次数、创建/开始/结束时间、
输出版本、错误结构和审计关联标识。

```text
QUEUED → VALIDATING → RUNNING → STAGING → VERIFYING → SUCCEEDED
```

可恢复错误进入 `RETRY_WAIT`；用户取消经 `CANCEL_REQUESTED` 到 `CANCELLED`；无提交证据的重启遗留
任务为 `INTERRUPTED`；权限、契约、泄漏、完整性、时点错误直接 `FAILED`。相同去重键的并发请求
复用活动任务。只有校验通过且版本原子登记后才能 `SUCCEEDED`。
