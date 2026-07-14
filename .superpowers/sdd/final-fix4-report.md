# 多数据源行情接入最终安全修复（四）报告

## 修复范围

本次只关闭“规范化工件存在但不一定是当前返回报价”的溯源缺口。未增加真实网络、Finnhub HTTP、券商接入、交易或自动交易功能；未改动既有的新鲜度、来源隔离和凭据边界。

## 失败测试证据

先新增“父链、原始工件和规范化工件哈希均正确，但规范化工件为旧批次或空批次”的回归用例，再运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_sina_market_data_provenance.py -k 当前报价批次 -v
```

首次结果为 2 个失败用例，错误均为 `Failed: DID NOT RAISE SinaDataSourceError`。这证明此前仅校验工件存在、内容哈希与父链，不能证明回读的规范化工件就是本次将要返回的报价批次。

## 实现

- `SinaHttpAdapter` 对已规范化的当前整批报价使用稳定 JSON 规则序列化：固定紧凑分隔符、键排序、UTF-8 编码，并以 `model_dump(mode="json")` 写入每一条完整返回报价。因此事实载荷包含来源、数据版本、证券市场身份、市场时间、采集时间、新鲜度和当前 `NormalizedQuote` 的所有返回字段。
- 适配器自行计算该事实载荷的 SHA-256。`SinaFactRecorder` 接口改为接收此精确字节载荷；记录器只负责原样追加写入，不再构造或回传规范化批次哈希。
- 适配器完成持久化后，以同一 `VersioningService` 回读规范化工件，重新计算哈希并严格等于适配器自身的当前批次哈希；同时继续校验原始字节和父版本关联。工件缺失、回读/解析路径异常、哈希不匹配或父链不匹配都会统一转换为 `SinaDataSourceError`，整批报价不会返回。
- 新增空批次与不同报价批次两个回归用例；二者都具有正确的原始工件、版本和父链，但均被拒绝。既有真实落盘成功路径继续通过。

## 验证命令与结果

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
py -3.12 -m pytest
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
git diff --check
```

结果：聚焦测试 `29 passed`；全量测试 `105 passed`，总覆盖率 `90.05%`；Ruff 格式和静态检查均通过；差异空白检查通过。

## Concerns

- 规范化事实载荷以 SHA-256 绑定当前报价批次；其安全性依赖项目既有的 SHA-256 不可碰撞假设。
- 事实记录器仍须与适配器使用同一 `VersioningService` 数据根；数据根不一致会在回读验证时安全地拒绝报价。
