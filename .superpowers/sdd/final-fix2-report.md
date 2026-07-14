# 多数据源行情接入最终复审修复（二）报告

## 修复范围

本次只处理最终复审提出的行情新鲜度、Sina 本地事实持久化证明和年龄计算口径问题。未增加 Finnhub HTTP 或网络调用，未增加经纪商接入、下单或交易功能。

## 失败测试证据

先新增并运行以下测试：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py -v
```

首轮结果在收集阶段失败：`ImportError: cannot import name 'SinaPersistenceProof'`。该失败证明适配器尚未提供要求记录器返回且可验证的持久化证明契约。随后新增的非休市伪造 `NEAR_REALTIME`、`DELAYED`、`STALE` 状态和微秒年龄测试，用于约束修复后的行为。

## 实现

- 新增统一的 `calculate_age_seconds`：校验带时区、拒绝未来市场时间，并按真实时点差向上取整为秒；新鲜度分类、统一行情模型和 Sina 适配器共同使用该函数。
- `NormalizedQuote` 对所有非 `CLOSED` 状态按市场、市场时间和采集时间严格推导状态并比对。`CLOSED` 保留交易日历语义，但仍通过统一年龄函数拒绝未来时间。
- `SinaFactRecorder.record` 现在必须返回 `SinaPersistenceProof`，包括原始和规范化工件的版本、哈希及父版本关联。适配器仅在证明类型、原始响应哈希、版本关联和规范化哈希完整时返回行情。
- `SinaMarketDataFactRecorder` 继续使用既有 `VersioningService` 追加提交工件，并从两次提交结果构造证明；未新增平行存储体系。
- 成功路径测试已移除空记录器，改为真实 `SinaMarketDataFactRecorder(VersioningService(...))`，并验证带微秒采集时点得到统一的向上取整年龄。

## 验证命令与结果

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/contract/test_market_data_contract.py tests/failure/test_market_data_failures.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py -v
py -3.12 -m pytest
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
git diff --check
```

结果：相关行情测试 `68 passed`；全量测试 `101 passed`，覆盖率 `90.02%`；Ruff 格式和静态检查均通过；差异空白检查通过。

## 关注事项

- 适配器验证记录器返回的工件标识、哈希形态、原始响应哈希与父版本关联；实际追加提交仍由既有 `VersioningService` 负责。若未来增加新的记录器实现，必须遵守该证明契约，不能返回占位或空证明。
