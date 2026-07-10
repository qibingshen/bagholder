# 数据模型

## 统一约定

- 所有量化实体均携带 `source_id`、`market_time`、`collected_at_utc`、`dataset_version_id` 或等效版本引用。
- `instrument_id` 是全局证券主键；显示代码不是主键。时间同时保存市场当地带时区时间和 UTC。
- 可见数据只引用已校验、已提交版本；修订用 `parent_version_id` 形成新版本，禁止原地覆盖。
- `contract_version`、`request_id`、`task_id`、`correlation_id` 贯穿桌面、本地服务、工作者、训练与 MCP。

## 核心实体

| 实体 | 存储职责 | 关键字段与规则 |
|------|----------|----------------|
| Market | DuckDB | `market_id`、时区、币种、交易日历版本、交易阶段；A/HK/US 规则独立版本化 |
| Instrument | DuckDB | `instrument_id`、市场、交易所、供应商/显示代码、币种、证券类型、生效区间；代码变更为新关系 |
| TradingCalendarVersion | DuckDB + Parquet 工件 | 交易日、盘前/盘中/盘后、半日市、临时停市；历史计算固定日历版本 |
| DataSourceAuthorization | DuckDB + 平台凭据库引用 | 数据源、市场、最小读权限、凭据引用、状态、最近验证；不保存明文凭据 |
| DatasetVersion | DuckDB | 数据集、父版本、来源、市场时间范围、采集时间、模式、哈希、清单、质量状态、修订原因 |
| QuoteBatch / QuoteBar | Parquet + DuckDB 索引 | 原始与规范化行情分开；价格、成交量、市场时间、数据年龄、新鲜度、版本；按市场/日期/版本分区 |
| CorporateAction | DuckDB + Parquet | 拆股、分红、复权、停复牌、退市、代码变化及有效时间；按历史时点应用 |
| Sector / SectorMembership | DuckDB | 主板块和自定义板块；成员用 `valid_from`/`valid_to` 保存生效区间，永不覆盖历史 |
| FeatureSnapshot | Parquet + DuckDB 索引 | 特征定义版本、数据截止时点、输入版本清单、证券范围、哈希；不得含未来数据 |
| PredictionSnapshot | DuckDB + 可选 Parquet 解释工件 | 周期、三类概率、置信度、依据、风险、新鲜度、标签规则、数据/特征/模型版本、工具结果引用 |
| ActualOutcome | DuckDB | 关联预测快照；到期价格、标签、规则版本、状态；无有效到期价格时为 `PENDING_VALIDATION` |
| BacktestRun | DuckDB + Parquet 结果 | 窗口定义、数据截点、规则/成本版本、样本数、指标、输入版本清单、工件哈希 |
| ReportSnapshot | DuckDB + 文件工件 | 报告类型、涵盖市场、生成时间、数据版本、降级范围、免责声明、内容哈希 |
| Task | DuckDB | 类型、去重键、状态、尝试次数、输入/输出版本、错误码、恢复动作、审计关联标识 |
| ModelVersion | DuckDB 注册表 + 本地文件 | 候选/正式/已回滚状态、文件哈希、训练参数、代码、数据/特征/标签版本、评估证据 |
| ModelEvaluation | DuckDB + 工件 | Brier score、平衡准确率、市场/周期分组、影子交易日、严重故障、批准与发布审计 |
| AuditEvent | DuckDB | 追加式事件：授权、修订、任务迁移、批准、发布、回滚、恢复、MCP 拒绝 |
| DesktopSettings | SQLite | 窗口、偏好、过滤器、对话索引、通知状态；非量化事实 |
| BackupManifest | DuckDB + 备份清单 | 格式、哈希、包含版本、创建平台、恢复状态；凭据不包含在内 |

## 状态机

### 任务

```text
QUEUED → VALIDATING → RUNNING → STAGING → VERIFYING → SUCCEEDED
  ├→ RETRY_WAIT → QUEUED
  ├→ CANCEL_REQUESTED → CANCELLED
  └→ FAILED / INTERRUPTED
```

`FAILED` 用于契约、权限、完整性、时点和泄漏错误；`RETRY_WAIT` 仅用于可恢复网络、限频或短时源失败；
`INTERRUPTED` 重启后依据是否存在有效提交证据转换为重试或失败。

### 模型

```text
TRAINED → BACKTEST_PASSED → BASELINE_PASSED → SHADOW_RUNNING
→ SHADOW_PASSED → AWAITING_LOCAL_APPROVAL → RELEASED
```

失败进入 `GATE_FAILED` 或 `REJECTED`。发布门禁：Brier score 相对改善至少 5%，平衡准确率
增加至少 2 个百分点，单市场或周期不退化超过 2 个百分点，30 个交易日无严重故障影子运行，
且经本机桌面用户批准。回滚只切换至既有已验证版本。

## 物理目录与生命周期

```text
<用户数据根>/
├── data/       # DuckDB、Parquet、模型注册表与模型工件
├── settings/   # SQLite
├── backups/    # 备份包和清单
├── logs/       # 脱敏 JSON Lines
├── staging/    # 未提交任务输出，仅内部可见
├── cache/      # 可重建缓存
└── runtime/    # 锁、PID、短期本机通信信息，不备份
```

用户数据根由 `PlatformPaths` 集中解析：Windows 使用用户本地应用数据目录，macOS 使用
`~/Library/Application Support/<AppName>`，Linux 遵循 XDG 目录。安装包不保存可变业务数据。

## 数据校验规则

- 行情主键至少覆盖 `instrument_id`、市场时间、粒度、来源、版本；市场/采集时间、来源、版本缺失即拒绝提交。
- 交易时段内按规格阈值计算实时、准实时、延迟、过期；过期数据不能产生当前预测。
- 预测概率非负、总和在 100% ±0.1 个百分点内；必须有风险提示、模型/数据/特征版本和依据。
- 交叉市场金额比较必须有正确时点的汇率版本，否则返回不可比较。
- 备份恢复在隔离目录验证清单、哈希、模式兼容与引用完整性；失败不修改当前有效根目录。
