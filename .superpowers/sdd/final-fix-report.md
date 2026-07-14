# 多数据源行情接入最终修复报告

## 修复范围

本次仅处理最终审查的四项问题：时点一致性、本地溯源、来源与市场不混用、Finnhub 凭据删除失败处理。未实现 Finnhub HTTP、券商接入、下单或自动交易。

## 失败测试证据

先新增或收紧以下测试，再运行指定测试集合：

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/contract/test_market_data_contract.py tests/contract/test_data_source_credentials.py tests/integration/test_sina_market_data_provenance.py -v
```

首轮结果为预期失败：

- `SourceCapabilityViolationError` 与 `SinaMarketDataFactRecorder` 尚不存在，测试收集失败。
- 单独运行时，休市的未来市场时间没有抛出 `FreshnessClassificationError`。
- 钥匙串删除失败后，`DataSourceCredentialService` 不存在 `retry_pending_revocation`。

这些失败证明新测试先于对应实现存在。

## 实现

- `classify_freshness` 无论开闭市先校验带时区且市场时间不晚于采集时间，随后才返回 `CLOSED`；CN 5 秒、HK/US 15 秒实时阈值保持不变。
- `NormalizedQuote` 以市场时间和采集时间实际差值（向上取整秒）校验 `freshness.age_seconds`，拒绝未来时点和可伪造的新鲜度年龄。
- `MarketDataRegistry.fetch_quotes` 在调用前检查市场 capability，并在返回后逐条校验 `source_id` 与证券市场；任一不一致即整批失败。
- 新增 `SinaMarketDataFactRecorder`，通过既有 `VersioningService` 将原始新浪字节与规范化 JSON 分别追加写入不可变工件。规范化工件记录来源、市场时间、采集时间、数据版本、原始工件版本与内容哈希；保存异常会让适配器拒绝返回报价。
- `SinaHttpAdapter` 必须注入事实记录端口，消除未持久化的成功读取路径。
- Finnhub 删除凭据时先把私有引用移动到内部待撤销集合；删除失败时公开授权状态仍为“受限”，并可由 `retry_pending_revocation` 重试。公开对象和选择记录均不包含密钥或钥匙串引用。

## 验证命令与结果

```powershell
py -3.12 -m pytest
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
git diff --check
```

结果：`95 passed`，总覆盖率 `89.81%`（门槛 80%）；Ruff 格式与静态检查通过；差异空白检查通过。

## 未解决事项

- 事实记录器尚未接入应用启动组合根；当前适配器构造函数要求调用方显式注入，避免出现无持久化读取。后续接入真实新浪读取器时必须注入项目本地 `VersioningService` 包装的记录器。
- 原始工件成功、规范化工件提交失败时会保留可审计的孤立原始工件，但适配器不会返回任何行情；该行为符合追加式事实链和“不返回未持久化行情”边界。
