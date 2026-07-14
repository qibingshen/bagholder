# 多数据源行情接入最终安全修复（三）报告

## 修复范围

本次只修复 Sina 行情适配器把 `SinaPersistenceProof` 的字段形态当作持久化事实的问题。未增加 Finnhub HTTP、真实网络调用、交易功能或密钥处理。

## 失败测试证据

先新增以下回归用例，再修改生产代码：

- 证明字段和原始响应 SHA-256 均正确、但 `VersioningService` 中没有原始或规范化工件时，必须抛出 `SinaDataSourceError`。
- 工件已经通过既有 `VersioningService` 写入，但返回的规范化哈希被篡改时，必须抛出 `SinaDataSourceError`。
- 工件已经写入、证明中的父版本正确、但规范化工件元数据的父版本不是原始工件版本时，必须抛出 `SinaDataSourceError`。

新增测试后的首次执行：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_sina_market_data_provenance.py -v
```

结果：新增的 3 个用例均因 `SinaHttpAdapter.__init__()` 尚不接受
`versioning_service` 而失败，错误为
`TypeError: unexpected keyword argument 'versioning_service'`。这证明测试要求的受控验证端口尚未存在。

## 实现

- `SinaHttpAdapter` 构造函数现在强制接收 `VersioningService`；调用方不能仅传入一个返回形态正确证明的记录器而绕过验证。
- 适配器在记录器返回证明后，使用同一个既有 `VersioningService` 验证原始和规范化版本都存在，再回读两份工件，计算 SHA-256 并与证明匹配。
- 适配器读取规范化版本元数据，要求其 `parent_version_id` 与原始版本严格相等。工件缺失、哈希不符或父版本不符时均抛出 `SinaDataSourceError`，因此整批行情不会返回。
- `SinaMarketDataFactRecorder` 仍然是唯一的真实写入实现，继续使用既有 `VersioningService` 和本地工件目录；没有新建平行存储。
- 既有成功路径测试改为向适配器传入记录器绑定的同一 `VersioningService`，验证真实落盘路径仍可返回行情。

## 验证命令与结果

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
py -3.12 -m pytest
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
git diff --check
```

结果：聚焦行情测试 `28 passed`；全量测试 `104 passed`，覆盖率 `90.20%`；Ruff 格式检查和静态检查均通过；差异空白检查通过。

## Concerns

- 组合根在创建 `SinaHttpAdapter` 时必须向记录器和适配器传入同一个本地 `VersioningService`。若两者绑定不同数据根，验证会失败并安全地拒绝返回行情。
