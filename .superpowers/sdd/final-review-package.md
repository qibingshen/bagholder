# 多数据源行情接入最终复审包（第四次修复后）

基线：9dc4049

## 提交

7a77622 fix: bind sina quotes to persisted batch
261e5b7 fix: verify sina persisted artifacts
498e338 fix: harden market data freshness evidence
6a5ad1d fix: harden market data provenance boundaries
4368ebb fix: clear stale finnhub authorization
e103cfd fix: restrict market source credential state
1ab6b5a feat: configure sina and finnhub market sources
331f1be feat: add sina a-share market data adapter
d5c86cf fix: tighten sina code validation
d67b9b1 docs: add task 2 report
29ecc09 feat: enforce freshness and sina code rules
161ffa0 test: cover hk quote freshness boundary
d7b0a4c fix: validate quote freshness by market
f0415b7 fix: require quote freshness
525490b feat: add market data adapter registry

## 统计

 .superpowers/sdd/final-fix-report.md               |  46 +++
 .superpowers/sdd/final-fix2-report.md              |  39 +++
 .superpowers/sdd/final-fix3-report.md              |  47 ++++
 .superpowers/sdd/final-fix4-report.md              |  39 +++
 .superpowers/sdd/task-2-report.md                  |  82 ++++++
 .superpowers/sdd/task-3-report.md                  |  49 ++++
 .superpowers/sdd/task-4-report.md                  |  92 ++++++
 docs/acceptance/data-source-selection.md           |  23 ++
 src/stock_agent/adapters/market_data/__init__.py   |  13 +
 src/stock_agent/adapters/market_data/base.py       |  72 +++++
 src/stock_agent/adapters/market_data/registry.py   |  64 +++++
 .../adapters/market_data/sina_adapter.py           | 233 ++++++++++++++++
 src/stock_agent/adapters/market_data/sina_codes.py |  25 ++
 .../adapters/market_data/sina_provenance.py        |  48 ++++
 .../application/data_source_credential_service.py  | 174 ++++++++++++
 src/stock_agent/desktop/pages/data_source_page.py  |  24 ++
 src/stock_agent/domain/freshness.py                |  59 ++++
 tests/contract/test_data_source_credentials.py     | 180 ++++++++++++
 tests/contract/test_market_data_contract.py        | 309 +++++++++++++++++++++
 tests/failure/test_market_data_failures.py         | 108 +++++++
 .../test_sina_market_data_provenance.py            | 206 ++++++++++++++
 .../test_single_market_daily_pipeline.py           |  46 +++
 tests/property/test_freshness_rules.py             |  97 +++++++
 23 files changed, 2075 insertions(+)

## 差异

```diff
diff --git a/.superpowers/sdd/final-fix-report.md b/.superpowers/sdd/final-fix-report.md
new file mode 100644
index 0000000..8c0d55a
--- /dev/null
+++ b/.superpowers/sdd/final-fix-report.md
@@ -0,0 +1,46 @@
+# 多数据源行情接入最终修复报告
+
+## 修复范围
+
+本次仅处理最终审查的四项问题：时点一致性、本地溯源、来源与市场不混用、Finnhub 凭据删除失败处理。未实现 Finnhub HTTP、券商接入、下单或自动交易。
+
+## 失败测试证据
+
+先新增或收紧以下测试，再运行指定测试集合：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/contract/test_market_data_contract.py tests/contract/test_data_source_credentials.py tests/integration/test_sina_market_data_provenance.py -v
+```
+
+首轮结果为预期失败：
+
+- `SourceCapabilityViolationError` 与 `SinaMarketDataFactRecorder` 尚不存在，测试收集失败。
+- 单独运行时，休市的未来市场时间没有抛出 `FreshnessClassificationError`。
+- 钥匙串删除失败后，`DataSourceCredentialService` 不存在 `retry_pending_revocation`。
+
+这些失败证明新测试先于对应实现存在。
+
+## 实现
+
+- `classify_freshness` 无论开闭市先校验带时区且市场时间不晚于采集时间，随后才返回 `CLOSED`；CN 5 秒、HK/US 15 秒实时阈值保持不变。
+- `NormalizedQuote` 以市场时间和采集时间实际差值（向上取整秒）校验 `freshness.age_seconds`，拒绝未来时点和可伪造的新鲜度年龄。
+- `MarketDataRegistry.fetch_quotes` 在调用前检查市场 capability，并在返回后逐条校验 `source_id` 与证券市场；任一不一致即整批失败。
+- 新增 `SinaMarketDataFactRecorder`，通过既有 `VersioningService` 将原始新浪字节与规范化 JSON 分别追加写入不可变工件。规范化工件记录来源、市场时间、采集时间、数据版本、原始工件版本与内容哈希；保存异常会让适配器拒绝返回报价。
+- `SinaHttpAdapter` 必须注入事实记录端口，消除未持久化的成功读取路径。
+- Finnhub 删除凭据时先把私有引用移动到内部待撤销集合；删除失败时公开授权状态仍为“受限”，并可由 `retry_pending_revocation` 重试。公开对象和选择记录均不包含密钥或钥匙串引用。
+
+## 验证命令与结果
+
+```powershell
+py -3.12 -m pytest
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+结果：`95 passed`，总覆盖率 `89.81%`（门槛 80%）；Ruff 格式与静态检查通过；差异空白检查通过。
+
+## 未解决事项
+
+- 事实记录器尚未接入应用启动组合根；当前适配器构造函数要求调用方显式注入，避免出现无持久化读取。后续接入真实新浪读取器时必须注入项目本地 `VersioningService` 包装的记录器。
+- 原始工件成功、规范化工件提交失败时会保留可审计的孤立原始工件，但适配器不会返回任何行情；该行为符合追加式事实链和“不返回未持久化行情”边界。
diff --git a/.superpowers/sdd/final-fix2-report.md b/.superpowers/sdd/final-fix2-report.md
new file mode 100644
index 0000000..552e601
--- /dev/null
+++ b/.superpowers/sdd/final-fix2-report.md
@@ -0,0 +1,39 @@
+# 多数据源行情接入最终复审修复（二）报告
+
+## 修复范围
+
+本次只处理最终复审提出的行情新鲜度、Sina 本地事实持久化证明和年龄计算口径问题。未增加 Finnhub HTTP 或网络调用，未增加经纪商接入、下单或交易功能。
+
+## 失败测试证据
+
+先新增并运行以下测试：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py -v
+```
+
+首轮结果在收集阶段失败：`ImportError: cannot import name 'SinaPersistenceProof'`。该失败证明适配器尚未提供要求记录器返回且可验证的持久化证明契约。随后新增的非休市伪造 `NEAR_REALTIME`、`DELAYED`、`STALE` 状态和微秒年龄测试，用于约束修复后的行为。
+
+## 实现
+
+- 新增统一的 `calculate_age_seconds`：校验带时区、拒绝未来市场时间，并按真实时点差向上取整为秒；新鲜度分类、统一行情模型和 Sina 适配器共同使用该函数。
+- `NormalizedQuote` 对所有非 `CLOSED` 状态按市场、市场时间和采集时间严格推导状态并比对。`CLOSED` 保留交易日历语义，但仍通过统一年龄函数拒绝未来时间。
+- `SinaFactRecorder.record` 现在必须返回 `SinaPersistenceProof`，包括原始和规范化工件的版本、哈希及父版本关联。适配器仅在证明类型、原始响应哈希、版本关联和规范化哈希完整时返回行情。
+- `SinaMarketDataFactRecorder` 继续使用既有 `VersioningService` 追加提交工件，并从两次提交结果构造证明；未新增平行存储体系。
+- 成功路径测试已移除空记录器，改为真实 `SinaMarketDataFactRecorder(VersioningService(...))`，并验证带微秒采集时点得到统一的向上取整年龄。
+
+## 验证命令与结果
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/contract/test_market_data_contract.py tests/failure/test_market_data_failures.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py -v
+py -3.12 -m pytest
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+结果：相关行情测试 `68 passed`；全量测试 `101 passed`，覆盖率 `90.02%`；Ruff 格式和静态检查均通过；差异空白检查通过。
+
+## 关注事项
+
+- 适配器验证记录器返回的工件标识、哈希形态、原始响应哈希与父版本关联；实际追加提交仍由既有 `VersioningService` 负责。若未来增加新的记录器实现，必须遵守该证明契约，不能返回占位或空证明。
diff --git a/.superpowers/sdd/final-fix3-report.md b/.superpowers/sdd/final-fix3-report.md
new file mode 100644
index 0000000..0c83301
--- /dev/null
+++ b/.superpowers/sdd/final-fix3-report.md
@@ -0,0 +1,47 @@
+# 多数据源行情接入最终安全修复（三）报告
+
+## 修复范围
+
+本次只修复 Sina 行情适配器把 `SinaPersistenceProof` 的字段形态当作持久化事实的问题。未增加 Finnhub HTTP、真实网络调用、交易功能或密钥处理。
+
+## 失败测试证据
+
+先新增以下回归用例，再修改生产代码：
+
+- 证明字段和原始响应 SHA-256 均正确、但 `VersioningService` 中没有原始或规范化工件时，必须抛出 `SinaDataSourceError`。
+- 工件已经通过既有 `VersioningService` 写入，但返回的规范化哈希被篡改时，必须抛出 `SinaDataSourceError`。
+- 工件已经写入、证明中的父版本正确、但规范化工件元数据的父版本不是原始工件版本时，必须抛出 `SinaDataSourceError`。
+
+新增测试后的首次执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_sina_market_data_provenance.py -v
+```
+
+结果：新增的 3 个用例均因 `SinaHttpAdapter.__init__()` 尚不接受
+`versioning_service` 而失败，错误为
+`TypeError: unexpected keyword argument 'versioning_service'`。这证明测试要求的受控验证端口尚未存在。
+
+## 实现
+
+- `SinaHttpAdapter` 构造函数现在强制接收 `VersioningService`；调用方不能仅传入一个返回形态正确证明的记录器而绕过验证。
+- 适配器在记录器返回证明后，使用同一个既有 `VersioningService` 验证原始和规范化版本都存在，再回读两份工件，计算 SHA-256 并与证明匹配。
+- 适配器读取规范化版本元数据，要求其 `parent_version_id` 与原始版本严格相等。工件缺失、哈希不符或父版本不符时均抛出 `SinaDataSourceError`，因此整批行情不会返回。
+- `SinaMarketDataFactRecorder` 仍然是唯一的真实写入实现，继续使用既有 `VersioningService` 和本地工件目录；没有新建平行存储。
+- 既有成功路径测试改为向适配器传入记录器绑定的同一 `VersioningService`，验证真实落盘路径仍可返回行情。
+
+## 验证命令与结果
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
+py -3.12 -m pytest
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+结果：聚焦行情测试 `28 passed`；全量测试 `104 passed`，覆盖率 `90.20%`；Ruff 格式检查和静态检查均通过；差异空白检查通过。
+
+## Concerns
+
+- 组合根在创建 `SinaHttpAdapter` 时必须向记录器和适配器传入同一个本地 `VersioningService`。若两者绑定不同数据根，验证会失败并安全地拒绝返回行情。
diff --git a/.superpowers/sdd/final-fix4-report.md b/.superpowers/sdd/final-fix4-report.md
new file mode 100644
index 0000000..9225d3b
--- /dev/null
+++ b/.superpowers/sdd/final-fix4-report.md
@@ -0,0 +1,39 @@
+# 多数据源行情接入最终安全修复（四）报告
+
+## 修复范围
+
+本次只关闭“规范化工件存在但不一定是当前返回报价”的溯源缺口。未增加真实网络、Finnhub HTTP、券商接入、交易或自动交易功能；未改动既有的新鲜度、来源隔离和凭据边界。
+
+## 失败测试证据
+
+先新增“父链、原始工件和规范化工件哈希均正确，但规范化工件为旧批次或空批次”的回归用例，再运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_sina_market_data_provenance.py -k 当前报价批次 -v
+```
+
+首次结果为 2 个失败用例，错误均为 `Failed: DID NOT RAISE SinaDataSourceError`。这证明此前仅校验工件存在、内容哈希与父链，不能证明回读的规范化工件就是本次将要返回的报价批次。
+
+## 实现
+
+- `SinaHttpAdapter` 对已规范化的当前整批报价使用稳定 JSON 规则序列化：固定紧凑分隔符、键排序、UTF-8 编码，并以 `model_dump(mode="json")` 写入每一条完整返回报价。因此事实载荷包含来源、数据版本、证券市场身份、市场时间、采集时间、新鲜度和当前 `NormalizedQuote` 的所有返回字段。
+- 适配器自行计算该事实载荷的 SHA-256。`SinaFactRecorder` 接口改为接收此精确字节载荷；记录器只负责原样追加写入，不再构造或回传规范化批次哈希。
+- 适配器完成持久化后，以同一 `VersioningService` 回读规范化工件，重新计算哈希并严格等于适配器自身的当前批次哈希；同时继续校验原始字节和父版本关联。工件缺失、回读/解析路径异常、哈希不匹配或父链不匹配都会统一转换为 `SinaDataSourceError`，整批报价不会返回。
+- 新增空批次与不同报价批次两个回归用例；二者都具有正确的原始工件、版本和父链，但均被拒绝。既有真实落盘成功路径继续通过。
+
+## 验证命令与结果
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
+py -3.12 -m pytest
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+结果：聚焦测试 `29 passed`；全量测试 `105 passed`，总覆盖率 `90.05%`；Ruff 格式和静态检查均通过；差异空白检查通过。
+
+## Concerns
+
+- 规范化事实载荷以 SHA-256 绑定当前报价批次；其安全性依赖项目既有的 SHA-256 不可碰撞假设。
+- 事实记录器仍须与适配器使用同一 `VersioningService` 数据根；数据根不一致会在回读验证时安全地拒绝报价。
diff --git a/.superpowers/sdd/task-2-report.md b/.superpowers/sdd/task-2-report.md
new file mode 100644
index 0000000..dc1d53d
--- /dev/null
+++ b/.superpowers/sdd/task-2-report.md
@@ -0,0 +1,82 @@
+# Task 2 完成报告：新鲜度与新浪代码规则
+
+## 范围与文件
+
+- `src/stock_agent/domain/freshness.py`：跨市场新鲜度纯分类规则。
+- `src/stock_agent/adapters/market_data/sina_codes.py`：新浪 A 股请求代码纯规范化规则。
+- `tests/property/test_freshness_rules.py`：新鲜度阈值、休市和时间错误测试。
+- `tests/failure/test_market_data_failures.py`：新浪代码合法映射与拒绝测试。
+
+未实现 HTTP、供应商响应解析、存储、凭据、券商、下单或自动交易功能。
+
+## TDD 证据
+
+1. 先新增两份测试文件并执行指定 pytest 命令。
+2. 初次执行在收集阶段失败：`ModuleNotFoundError`，缺少
+   `stock_agent.domain.freshness` 与
+   `stock_agent.adapters.market_data.sina_codes`，证明测试先于实现存在。
+3. 写入最小纯规则实现后，补充“休市时优先返回 `CLOSED`”测试；该测试先因
+   `FreshnessClassificationError` 失败，再将休市分支移动到时间校验之前。
+4. 最终指定测试全部通过。
+
+## 验证证据
+
+执行时间：2026-07-14。
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py -v
+```
+
+结果：`21 passed in 0.67s`。
+
+```powershell
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+```
+
+结果：格式检查显示 `53 files already formatted`，静态检查退出码为 0 且无诊断。
+
+## 自检
+
+- CN 在 5 秒、HK/US 在 15 秒仍为 `REALTIME`，超限为 `NEAR_REALTIME`。
+- 60 秒为 `NEAR_REALTIME`，61 秒至 900 秒为 `DELAYED`，901 秒为 `STALE`。
+- 休市一律为 `CLOSED`；开市时无时区与负年龄均抛出领域错误。
+- 仅 CN 的 SSE/SZSE 六位数字代码映射为 `sh`/`sz` 前缀；其他市场、交易所和代码均拒绝。
+- 已执行暂存差异空白检查，任务实现提交未包含范围外文件。
+
+## 提交哈希
+
+- `29ecc09863bb448f10e8acc262f805d8dc0973e9`：`feat: enforce freshness and sina code rules`
+
+## Concerns
+
+- 无已知功能性 concern。
+- 工作区中存在其他代理或用户的未跟踪、已修改文件；本任务提交未包含它们。
+
+## 复核修复记录
+
+### 修复内容
+
+- 新浪代码六位校验改为逐字符严格 ASCII `0-9` 判断，不再接受 Unicode 十进制数字。
+- 新鲜度测试补充 CN/HK/US 开市时年龄为 0 秒的 `REALTIME` 边界。
+- 新鲜度测试补充 `collected_at` 无时区时必须拒绝的场景。
+- 新浪代码拒绝测试补充全角数字 `１２３４５６`。
+
+### 复核 TDD 证据
+
+新增全角数字拒绝用例后，指定 pytest 命令先失败：该用例未抛出
+`UnsupportedSinaCodeError`，原因是原实现使用 `isdecimal()` 接受全角数字。收紧
+ASCII 校验后，指定 pytest 命令通过。
+
+### 复核验证证据
+
+执行时间：2026-07-14。
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+```
+
+结果：`26 passed in 0.58s`；格式检查显示 `53 files already formatted`；静态检查退出码为
+0 且无诊断。
diff --git a/.superpowers/sdd/task-3-report.md b/.superpowers/sdd/task-3-report.md
new file mode 100644
index 0000000..d0fdfdf
--- /dev/null
+++ b/.superpowers/sdd/task-3-report.md
@@ -0,0 +1,49 @@
+# Task 3 新浪 HTTP 适配器报告
+
+## 变更文件
+
+- `src/stock_agent/adapters/market_data/sina_adapter.py`
+- `tests/integration/test_single_market_daily_pipeline.py`
+- `tests/failure/test_market_data_failures.py`
+
+## 实现摘要
+
+- 新增只读 `SinaHttpAdapter`，仅通过注入的 `http_get` 发起受控新浪 HTTP GET。
+- 严格校验请求代码、GBK 响应、响应行、必要字段和日期时间；任一失败均抛出 `SinaDataSourceError`，不返回部分行情。
+- 将沪深代码映射为 `Market.CN` 证券身份，以 `Asia/Shanghai` 构造市场时间，并调用 `classify_freshness` 生成新鲜度。
+- 以原始响应的 SHA-256 生成非空新浪数据版本标识。
+
+## TDD 证据
+
+先新增适配器导入与边界测试，再运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
+```
+
+首次运行在收集阶段失败，原因是 `ModuleNotFoundError: No module named 'stock_agent.adapters.market_data.sina_adapter'`，证明测试覆盖了尚未实现的接口。完成最小实现后，同一命令通过 21 项测试。
+
+## 验证命令
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+最终验证结果：21 passed；Ruff 格式检查通过；Ruff 静态检查通过；差异空白检查通过。
+
+## 自检
+
+- 未访问真实网络，测试读取器均为本地注入函数。
+- 未实现历史日线、复权、公司行为、存储、凭据、券商、订单或自动交易能力。
+- 未修改任务范围外的项目文件；工作区中既有的其他未提交变更未纳入本任务。
+
+## 提交
+
+本报告随提交 `feat: add sina a-share market data adapter` 一并提交；最终哈希以 Git 当前提交为准。
+
+## Concerns
+
+无。
diff --git a/.superpowers/sdd/task-4-report.md b/.superpowers/sdd/task-4-report.md
new file mode 100644
index 0000000..195f630
--- /dev/null
+++ b/.superpowers/sdd/task-4-report.md
@@ -0,0 +1,92 @@
+# Task 4：新浪与 Finnhub 配置及选择证据报告
+
+## 完成文件
+
+- `src/stock_agent/application/data_source_credential_service.py`
+- `src/stock_agent/desktop/pages/data_source_page.py`
+- `tests/contract/test_data_source_credentials.py`
+- `docs/acceptance/data-source-selection.md`
+
+## 实现摘要
+
+- 增加不可变数据源元数据：新浪仅支持 `CN`、公开只读且不保证实时；Finnhub 仅支持 `US`、需要凭据且未授权时受限。
+- 增加不含明文密钥和钥匙串引用的选择记录，包含市场、凭据需求、访问状态、降级说明和审计说明。
+- Finnhub 配置后显示“已授权”，撤销后恢复“受限”；新浪拒绝凭据配置。
+- 页面新增从脱敏选择记录生成摘要的入口，不展示明文密钥或钥匙串引用。
+- 补充验收文档，明确 URL 能力、市场时间与新鲜度限制、合法密钥、无密钥降级、不混用和不绕过许可。
+
+## TDD 证据
+
+先在 `tests/contract/test_data_source_credentials.py` 添加新浪元数据与 Finnhub 授权生命周期测试，再运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py -v
+```
+
+失败结果：新增两个测试均因 `DataSourceCredentialService` 缺少 `selection_record` 报 `AttributeError`；原有四个测试通过。随后完成最小实现。
+
+## 验证命令与结果
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+```
+
+结果：8 个测试全部通过；Ruff 格式检查通过（55 个文件已格式化）；Ruff 静态检查通过。
+
+## 自检
+
+- 选择记录和页面摘要均不从 `CredentialAuthorization.credential_reference` 取值。
+- 本任务未新增 Finnhub HTTP、网络、券商、交易、下单或自动交易实现。
+- 仅修改任务要求的 4 个业务、测试和文档文件，并新增本报告。
+
+## Concerns
+
+- 当前桌面层仅提供页面状态模型；实际 PySide6 视图尚未在本任务范围内，因此调用方需要使用 `from_selection_record` 渲染选择摘要。
+
+## 修复与复验
+
+审查修复后，公开的 `CredentialAuthorization` 仅包含 `source_id` 和 `is_authorized`；钥匙串引用仅存于服务内部私有映射。配置仅允许 Finnhub 且要求 `KeyringCredentialStore`，新浪、未知源和非钥匙串存储均明确失败。撤销仅允许 Finnhub，查询和选择记录仅允许受控数据源。页面移除了 `from_authorization`，只接收脱敏的选择记录，因此新浪会保留“公开只读”状态。
+
+本次先替换契约测试并执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py -v
+```
+
+红灯结果：5 项中 4 项失败，分别证明公开对象仍暴露钥匙串引用、Finnhub 配置引用泄露、未知源可配置，以及页面仍存在 `from_authorization`；新浪选择记录测试通过。
+
+最小修复后执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+复验结果：7 项测试全部通过；Ruff 格式检查通过（55 个文件已格式化）；Ruff 静态检查通过；差异检查通过。
+
+## 修复与复验（二）
+
+重配 Finnhub 时，服务现在先从私有引用映射移除旧引用，再删除旧钥匙串项并写入新密钥。新密钥写入失败时不会遗留陈旧引用，因此公开 `status()` 返回未授权，选择记录返回“受限”；公开对象和选择记录仍不包含密钥或钥匙串引用。
+
+先添加失败场景测试并执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py -v
+```
+
+红灯结果：新增“Finnhub 重配写入失败后公开状态恢复受限且不泄露引用”测试失败，实际 `is_authorized` 为 `True`，证明旧私有引用仍导致伪授权。
+
+最小修复并格式化后执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+复验结果：8 项测试全部通过；Ruff 格式检查通过（55 个文件已格式化）；Ruff 静态检查通过；差异检查通过。
diff --git a/docs/acceptance/data-source-selection.md b/docs/acceptance/data-source-selection.md
new file mode 100644
index 0000000..65e5e31
--- /dev/null
+++ b/docs/acceptance/data-source-selection.md
@@ -0,0 +1,23 @@
+# 数据源选择验收说明
+
+## 配置边界
+
+| 数据源 | 市场 | 凭据 | 初始访问状态 | 降级说明 |
+| --- | --- | --- | --- | --- |
+| 新浪 | `CN` | 不需要 | 公开只读 | 新浪 URL 仅作为公开只读 A 股候选能力，受市场时间和数据新鲜度限制，不保证实时。 |
+| Finnhub | `US` | 需要 | 受限 | 用户未配置合法密钥时，保持受限，不提供美股实时数据。 |
+
+新浪不接受凭据配置。Finnhub 的用户自带合法密钥仅通过 `KeyringCredentialStore` 写入系统钥匙串；服务内部私有记录可撤销引用，公开状态、页面摘要和审计选择记录均不写入明文密钥或钥匙串引用。
+
+## 选择记录
+
+选择记录固定包含数据源标识、支持市场、是否需要凭据、访问状态、降级说明和审计说明。新浪记录说明 URL 能力及市场时间、新鲜度限制；Finnhub 记录说明用户自带合法密钥、无密钥降级、数据源不混用且不绕过许可。
+
+## 验收步骤
+
+1. 查询新浪选择记录，确认市场为 `CN`、状态为“公开只读”，并包含“不保证实时”。
+2. 未配置 Finnhub 密钥时查询选择记录，确认市场为 `US`、状态为“受限”。
+3. 通过系统钥匙串配置 Finnhub 密钥后，确认状态变为“已授权”；页面中不得出现密钥或 `platform-keychain://`。
+4. 撤销 Finnhub 授权后，确认状态恢复为“受限”。
+
+本任务不实现 Finnhub HTTP 调用、真实网络访问、券商或任何交易、下单和自动交易能力。
diff --git a/src/stock_agent/adapters/market_data/__init__.py b/src/stock_agent/adapters/market_data/__init__.py
new file mode 100644
index 0000000..d0fbd33
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/__init__.py
@@ -0,0 +1,13 @@
+"""导出供应商无关的行情适配器协议和注册表。"""
+
+from .base import MarketDataAdapter, NormalizedQuote, SourceCapability
+from .registry import DuplicateSourceError, MarketDataRegistry, UnknownSourceError
+
+__all__ = [
+    "DuplicateSourceError",
+    "MarketDataAdapter",
+    "MarketDataRegistry",
+    "NormalizedQuote",
+    "SourceCapability",
+    "UnknownSourceError",
+]
diff --git a/src/stock_agent/adapters/market_data/base.py b/src/stock_agent/adapters/market_data/base.py
new file mode 100644
index 0000000..7f28daa
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/base.py
@@ -0,0 +1,72 @@
+"""定义与供应商无关的行情适配器协议。"""
+
+from __future__ import annotations
+
+from collections.abc import Sequence
+from datetime import datetime
+from typing import Protocol
+
+from pydantic import BaseModel, Field, field_validator, model_validator
+
+from stock_agent.contracts.common import Freshness
+from stock_agent.domain.freshness import calculate_age_seconds, classify_freshness
+from stock_agent.domain.market import InstrumentIdentity
+
+
+class SourceCapability(BaseModel):
+    """描述行情来源可提供的市场范围和运行能力。"""
+
+    source_id: str = Field(min_length=1)
+    markets: tuple[str, ...] = Field(min_length=1)
+    credential_required: bool
+    supports_realtime: bool
+
+
+class NormalizedQuote(BaseModel):
+    """承载已规范化且可追溯的单个证券行情。"""
+
+    security_id: InstrumentIdentity
+    price: float
+    source_id: str = Field(min_length=1)
+    market_time: datetime
+    collected_at: datetime
+    data_version: str = Field(min_length=1)
+    freshness: Freshness
+
+    @field_validator("market_time", "collected_at")
+    @classmethod
+    def 验证时间包含时区(cls, value: datetime) -> datetime:
+        """拒绝无时区时间，防止跨市场数据按错误时点比较。"""
+
+        if value.tzinfo is None or value.utcoffset() is None:
+            raise ValueError("行情时间必须包含时区")
+        return value
+
+    @model_validator(mode="after")
+    def 验证行情新鲜度(self) -> NormalizedQuote:
+        """校验时点推导的新鲜度，防止延迟行情伪装成更高时效等级。"""
+
+        age_seconds = calculate_age_seconds(self.market_time, self.collected_at)
+        if self.freshness.age_seconds != age_seconds:
+            raise ValueError("行情新鲜度年龄必须与市场时间和采集时间一致")
+
+        if self.freshness.state == "CLOSED":
+            return self
+
+        expected_state = classify_freshness(
+            self.security_id.market, self.market_time, self.collected_at, is_open=True
+        )
+        if self.freshness.state != expected_state:
+            raise ValueError(f"实时行情新鲜度状态必须为 {expected_state}")
+        return self
+
+
+class MarketDataAdapter(Protocol):
+    """定义核心服务获取行情时依赖的最小供应商无关接口。"""
+
+    capability: SourceCapability
+
+    def fetch_quotes(
+        self, codes: Sequence[str], collected_at: datetime
+    ) -> Sequence[NormalizedQuote]:
+        """按证券代码获取已规范化行情，不暴露供应商原始字段。"""
diff --git a/src/stock_agent/adapters/market_data/registry.py b/src/stock_agent/adapters/market_data/registry.py
new file mode 100644
index 0000000..de32591
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/registry.py
@@ -0,0 +1,64 @@
+"""提供行情适配器的显式注册和查找。"""
+
+from __future__ import annotations
+
+from collections.abc import Sequence
+from datetime import datetime
+
+from stock_agent.adapters.market_data.base import NormalizedQuote
+from stock_agent.domain.market import Market
+
+from .base import MarketDataAdapter
+
+
+class DuplicateSourceError(ValueError):
+    """表示尝试重复注册同一行情来源。"""
+
+
+class UnknownSourceError(LookupError):
+    """表示请求的行情来源尚未注册。"""
+
+
+class SourceCapabilityViolationError(ValueError):
+    """表示适配器声明能力与实际返回行情不一致。"""
+
+
+class MarketDataRegistry:
+    """保存来源标识到行情适配器的受控映射。"""
+
+    def __init__(self) -> None:
+        """初始化空的适配器注册表。"""
+
+        self._adapters: dict[str, MarketDataAdapter] = {}
+
+    def register(self, adapter: MarketDataAdapter) -> None:
+        """注册适配器；同一来源标识重复注册时明确拒绝。"""
+
+        source_id = adapter.capability.source_id
+        if source_id in self._adapters:
+            raise DuplicateSourceError(f"行情来源已注册：{source_id}")
+        self._adapters[source_id] = adapter
+
+    def get(self, source_id: str) -> MarketDataAdapter:
+        """返回已注册适配器；未知来源时抛出明确领域错误。"""
+
+        try:
+            return self._adapters[source_id]
+        except KeyError as error:
+            raise UnknownSourceError(f"未知行情来源：{source_id}") from error
+
+    def fetch_quotes(
+        self, source_id: str, codes: Sequence[str], collected_at: datetime, market: Market
+    ) -> Sequence[NormalizedQuote]:
+        """只返回与选定来源及市场能力完全一致的一整批行情。"""
+
+        adapter = self.get(source_id)
+        if market.value not in adapter.capability.markets:
+            raise SourceCapabilityViolationError(f"行情来源不支持市场：{market.value}")
+        quotes = adapter.fetch_quotes(codes, collected_at)
+        if any(
+            quote.source_id != source_id or quote.security_id.market is not market
+            for quote in quotes
+        ):
+            raise SourceCapabilityViolationError("适配器返回了与来源或市场能力不一致的行情")
+        return quotes
diff --git a/src/stock_agent/adapters/market_data/sina_adapter.py b/src/stock_agent/adapters/market_data/sina_adapter.py
new file mode 100644
index 0000000..8b7c254
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/sina_adapter.py
@@ -0,0 +1,233 @@
+"""提供只读新浪 A 股行情 HTTP 适配器。"""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import math
+import re
+from collections.abc import Callable, Sequence
+from dataclasses import dataclass
+from datetime import datetime
+from typing import Protocol
+from zoneinfo import ZoneInfo
+
+from stock_agent.adapters.market_data.base import NormalizedQuote, SourceCapability
+from stock_agent.application.versioning_service import VersioningService
+from stock_agent.contracts.common import Freshness
+from stock_agent.domain.freshness import calculate_age_seconds, classify_freshness
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+_SINA_URL_PREFIX = "http://hq.sinajs.cn/list="
+_SINA_CODE_PATTERN = re.compile(r"(?P<prefix>sh|sz)(?P<display_code>[0-9]{6})\Z")
+_SINA_LINE_PATTERN = re.compile(
+    r'var hq_str_(?P<code>sh[0-9]{6}|sz[0-9]{6})="(?P<fields>[^"]*)";\Z'
+)
+_SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
+
+
+class SinaDataSourceError(RuntimeError):
+    """表示新浪读取结果无法安全转换为完整规范化行情。"""
+
+
+@dataclass(frozen=True, slots=True)
+class SinaPersistenceProof:
+    """描述已追加提交的原始和规范化行情工件及其版本关联。"""
+
+    raw_artifact_version_id: str
+    normalized_artifact_version_id: str
+    parent_version_id: str
+
+
+class SinaFactRecorder(Protocol):
+    """定义新浪行情事实记录端口，适配器不直接依赖具体本地实现。"""
+
+    def record(self, raw_response: bytes, normalized_content: bytes) -> SinaPersistenceProof:
+        """追加保存适配器生成的原始响应与规范化批次，并返回工件关联。"""
+
+
+class SinaHttpAdapter:
+    """通过调用方注入的读取器获取并验证新浪 A 股实时报价。"""
+
+    capability = SourceCapability(
+        source_id="sina",
+        markets=(Market.CN.value,),
+        credential_required=False,
+        supports_realtime=True,
+    )
+
+    def __init__(
+        self,
+        http_get: Callable[[str], bytes],
+        fact_recorder: SinaFactRecorder,
+        versioning_service: VersioningService,
+    ) -> None:
+        """绑定读取器、记录器和既有版本服务，拒绝无真实工件验证的读取路径。"""
+
+        self._http_get = http_get
+        self._fact_recorder = fact_recorder
+        self._versioning_service = versioning_service
+
+    def fetch_quotes(self, codes: list[str], collected_at: datetime) -> list[NormalizedQuote]:
+        """读取全部请求代码；任一异常均拒绝返回部分行情。"""
+
+        self._validate_codes(codes)
+        url = f"{_SINA_URL_PREFIX}{','.join(codes)}"
+        try:
+            raw_response = self._http_get(url)
+            if not isinstance(raw_response, bytes):
+                raise TypeError("HTTP 读取器必须返回字节串")
+            decoded_response = raw_response.decode("gbk")
+            parsed_fields = self._parse_response(decoded_response, codes)
+            data_version = f"sina-{hashlib.sha256(raw_response).hexdigest()}"
+            quotes = [
+                self._normalize_quote(code, parsed_fields[code], collected_at, data_version)
+                for code in codes
+            ]
+            normalized_content = self._serialize_normalized_batch(quotes)
+            normalized_content_hash = hashlib.sha256(normalized_content).hexdigest()
+            proof = self._fact_recorder.record(raw_response, normalized_content)
+            self._validate_persistence_proof(proof)
+            self._verify_persisted_artifacts(proof, raw_response, normalized_content_hash)
+            return quotes
+        except SinaDataSourceError:
+            raise
+        except Exception as error:
+            raise SinaDataSourceError("新浪行情响应或本地事实保存无效，拒绝生成量化行情") from error
+
+    @staticmethod
+    def _validate_persistence_proof(proof: SinaPersistenceProof) -> None:
+        """确认记录器返回了完整的原始、规范化工件与父版本关联证明。"""
+
+        if not isinstance(proof, SinaPersistenceProof):
+            raise SinaDataSourceError("新浪事实保存未返回可验证的持久化证明")
+        if (
+            not proof.raw_artifact_version_id
+            or not proof.normalized_artifact_version_id
+            or proof.parent_version_id != proof.raw_artifact_version_id
+        ):
+            raise SinaDataSourceError("新浪事实保存返回的持久化证明不完整")
+
+    def _verify_persisted_artifacts(
+        self,
+        proof: SinaPersistenceProof,
+        raw_response: bytes,
+        normalized_content_hash: str,
+    ) -> None:
+        """从既有版本服务回读工件和元数据，拒绝仅形态正确的伪造证明。"""
+
+        raw_dataset = "market-data-raw"
+        normalized_dataset = "market-data-normalized"
+        if not (
+            self._versioning_service.version_exists(raw_dataset, proof.raw_artifact_version_id)
+            and self._versioning_service.version_exists(
+                normalized_dataset, proof.normalized_artifact_version_id
+            )
+        ):
+            raise SinaDataSourceError("新浪事实工件未实际落盘")
+
+        raw_content = self._versioning_service.read_bytes(
+            raw_dataset, proof.raw_artifact_version_id
+        )
+        normalized_content = self._versioning_service.read_bytes(
+            normalized_dataset, proof.normalized_artifact_version_id
+        )
+        normalized_metadata = self._versioning_service.metadata_for(
+            normalized_dataset, proof.normalized_artifact_version_id
+        )
+        if (
+            hashlib.sha256(raw_content).hexdigest() != hashlib.sha256(raw_response).hexdigest()
+            or hashlib.sha256(normalized_content).hexdigest() != normalized_content_hash
+            or normalized_metadata["parent_version_id"] != proof.raw_artifact_version_id
+        ):
+            raise SinaDataSourceError("新浪事实工件与当前规范化报价批次或父版本关联不匹配")
+
+    @staticmethod
+    def _serialize_normalized_batch(quotes: Sequence[NormalizedQuote]) -> bytes:
+        """确定性序列化当前返回的完整报价批次，作为回读校验的唯一事实载荷。"""
+
+        if not quotes:
+            raise SinaDataSourceError("新浪规范化报价批次不能为空")
+        first = quotes[0]
+        if any(
+            quote.source_id != first.source_id or quote.data_version != first.data_version
+            for quote in quotes
+        ):
+            raise SinaDataSourceError("新浪规范化报价批次的来源或数据版本不一致")
+        return json.dumps(
+            {
+                "data_version": first.data_version,
+                "quotes": [quote.model_dump(mode="json") for quote in quotes],
+                "source_id": first.source_id,
+            },
+            ensure_ascii=False,
+            separators=(",", ":"),
+            sort_keys=True,
+        ).encode("utf-8")
+
+    @staticmethod
+    def _validate_codes(codes: list[str]) -> None:
+        if not codes or any(_SINA_CODE_PATTERN.fullmatch(code) is None for code in codes):
+            raise SinaDataSourceError("新浪请求代码必须为 sh 或 sz 加六位 ASCII 数字")
+        if len(set(codes)) != len(codes):
+            raise SinaDataSourceError("新浪请求代码不能重复")
+
+    @staticmethod
+    def _parse_response(response: str, codes: list[str]) -> dict[str, list[str]]:
+        if not response.strip():
+            raise SinaDataSourceError("新浪响应不能为空")
+
+        parsed: dict[str, list[str]] = {}
+        lines = [line.strip() for line in response.splitlines() if line.strip()]
+        for line in lines:
+            match = _SINA_LINE_PATTERN.fullmatch(line)
+            if match is None:
+                raise SinaDataSourceError("新浪响应格式错误")
+            code = match.group("code")
+            if code not in codes or code in parsed:
+                raise SinaDataSourceError("新浪响应包含未请求或重复的证券代码")
+            fields = match.group("fields").split(",")
+            if len(fields) <= 31 or not fields[0].strip():
+                raise SinaDataSourceError("新浪响应缺少证券名称或关键字段")
+            parsed[code] = fields
+
+        if set(parsed) != set(codes):
+            raise SinaDataSourceError("新浪响应缺少请求的证券行情")
+        return parsed
+
+    @staticmethod
+    def _normalize_quote(
+        code: str,
+        fields: list[str],
+        collected_at: datetime,
+        data_version: str,
+    ) -> NormalizedQuote:
+        try:
+            price = float(fields[3])
+            if not math.isfinite(price):
+                raise ValueError("价格必须为有限数值")
+            market_time = datetime.strptime(
+                f"{fields[30].strip()} {fields[31].strip()}", "%Y-%m-%d %H:%M:%S"
+            ).replace(tzinfo=_SHANGHAI_TIMEZONE)
+            freshness_state = classify_freshness(Market.CN, market_time, collected_at, is_open=True)
+            age_seconds = calculate_age_seconds(market_time, collected_at)
+            match = _SINA_CODE_PATTERN.fullmatch(code)
+            if match is None:
+                raise ValueError("响应代码格式错误")
+            exchange = "SSE" if match.group("prefix") == "sh" else "SZSE"
+            return NormalizedQuote(
+                security_id=InstrumentIdentity(
+                    market=Market.CN,
+                    exchange=exchange,
+                    display_code=match.group("display_code"),
+                    currency="CNY",
+                ),
+                price=price,
+                source_id="sina",
+                market_time=market_time,
+                collected_at=collected_at,
+                data_version=data_version,
+                freshness=Freshness(state=freshness_state, age_seconds=age_seconds),
+            )
+        except Exception as error:
+            raise SinaDataSourceError("新浪响应包含无法使用的价格或市场时间") from error
diff --git a/src/stock_agent/adapters/market_data/sina_codes.py b/src/stock_agent/adapters/market_data/sina_codes.py
new file mode 100644
index 0000000..454ed0f
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/sina_codes.py
@@ -0,0 +1,25 @@
+"""定义新浪 A 股请求代码的纯规范化规则。"""
+
+from __future__ import annotations
+
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+class UnsupportedSinaCodeError(ValueError):
+    """表示证券身份不能安全转换为新浪 A 股请求代码。"""
+
+
+def normalize_sina_code(identity: InstrumentIdentity) -> str:
+    """将沪深 A 股六码数字代码转换为新浪请求前缀格式。"""
+
+    if identity.market is not Market.CN:
+        raise UnsupportedSinaCodeError("新浪代码规则只支持中国市场")
+    if len(identity.display_code) != 6 or any(
+        character < "0" or character > "9" for character in identity.display_code
+    ):
+        raise UnsupportedSinaCodeError("新浪代码必须是六位数字")
+
+    prefix = {"SSE": "sh", "SZSE": "sz"}.get(identity.exchange)
+    if prefix is None:
+        raise UnsupportedSinaCodeError("新浪代码不支持该交易所")
+    return f"{prefix}{identity.display_code}"
diff --git a/src/stock_agent/adapters/market_data/sina_provenance.py b/src/stock_agent/adapters/market_data/sina_provenance.py
new file mode 100644
index 0000000..73ead60
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/sina_provenance.py
@@ -0,0 +1,48 @@
+"""将新浪原始响应和规范化行情写入既有本地版本事实链。"""
+
+from __future__ import annotations
+
+import hashlib
+from datetime import UTC, datetime
+
+from stock_agent.adapters.market_data.sina_adapter import SinaPersistenceProof
+from stock_agent.application.versioning_service import VersioningService
+
+
+class SinaMarketDataFactRecorder:
+    """使用版本服务追加保存一批新浪原始响应及其规范化结果。"""
+
+    def __init__(self, versioning_service: VersioningService) -> None:
+        """注入项目既有版本服务，避免行情适配器另建存储体系。"""
+
+        self._versioning_service = versioning_service
+
+    def record(self, raw_response: bytes, normalized_content: bytes) -> SinaPersistenceProof:
+        """先提交原始字节，再原样提交适配器提供的规范化事实载荷。"""
+
+        if not normalized_content:
+            raise ValueError("规范化事实载荷不能为空")
+        raw_hash = hashlib.sha256(raw_response).hexdigest()
+        suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f%z")
+        version_prefix = raw_hash[:16]
+        raw_version_id = f"sina-{version_prefix}-raw-{suffix}"
+        raw = self._versioning_service.commit_bytes(
+            dataset="market-data-raw",
+            version_id=raw_version_id,
+            content=raw_response,
+            source_id="sina",
+            expected_hash=raw_hash,
+        )
+        normalized_version_id = f"sina-{version_prefix}-normalized-{suffix}"
+        normalized = self._versioning_service.commit_bytes(
+            dataset="market-data-normalized",
+            version_id=normalized_version_id,
+            content=normalized_content,
+            source_id="sina",
+            parent_version_id=raw.version_id,
+        )
+        return SinaPersistenceProof(
+            raw_artifact_version_id=raw.version_id,
+            normalized_artifact_version_id=normalized.version_id,
+            parent_version_id=normalized.parent_version_id or "",
+        )
diff --git a/src/stock_agent/application/data_source_credential_service.py b/src/stock_agent/application/data_source_credential_service.py
new file mode 100644
index 0000000..2a2bfe3
--- /dev/null
+++ b/src/stock_agent/application/data_source_credential_service.py
@@ -0,0 +1,174 @@
+"""管理受控数据源授权，确保公开状态、审计和页面不携带密钥或钥匙串引用。"""
+
+from dataclasses import dataclass
+from types import MappingProxyType
+
+from stock_agent.adapters.platform.credential_store import (
+    CredentialStore,
+    KeyringCredentialStore,
+)
+
+
+@dataclass(frozen=True, slots=True)
+class CredentialRegistration:
+    """接收短生命周期的密钥输入，仅允许由 Finnhub 配置路径消费。"""
+
+    source_id: str
+    secret: str
+
+    def __post_init__(self) -> None:
+        if not self.source_id.strip() or not self.secret:
+            raise ValueError("数据源与凭据不能为空")
+
+
+@dataclass(frozen=True, slots=True)
+class CredentialAuthorization:
+    """面向普通调用方的脱敏授权状态，不包含密钥或钥匙串引用。"""
+
+    source_id: str
+    is_authorized: bool
+
+
+@dataclass(frozen=True, slots=True)
+class DataSourceMetadata:
+    """不可变的数据源配置，仅描述市场范围、授权边界和降级规则。"""
+
+    source_id: str
+    supported_markets: tuple[str, ...]
+    requires_credentials: bool
+    access_state: str
+    degradation_notice: str
+
+
+@dataclass(frozen=True, slots=True)
+class DataSourceSelectionRecord:
+    """可复核的数据源选择记录，不包含明文密钥或钥匙串引用。"""
+
+    source_id: str
+    supported_markets: tuple[str, ...]
+    requires_credentials: bool
+    access_state: str
+    degradation_notice: str
+    audit_note: str
+
+
+DATA_SOURCE_METADATA = MappingProxyType(
+    {
+        "sina": DataSourceMetadata(
+            source_id="sina",
+            supported_markets=("CN",),
+            requires_credentials=False,
+            access_state="公开只读",
+            degradation_notice="公开只读且不保证实时；仅作为 A 股候选数据源。",
+        ),
+        "finnhub": DataSourceMetadata(
+            source_id="finnhub",
+            supported_markets=("US",),
+            requires_credentials=True,
+            access_state="受限",
+            degradation_notice="无密钥降级为受限状态，不提供美股实时数据。",
+        ),
+    }
+)
+
+_SELECTION_AUDIT_NOTES = MappingProxyType(
+    {
+        "sina": "新浪 URL 仅支持公开只读能力；受市场时间与数据新鲜度限制，不保证实时。",
+        "finnhub": "Finnhub 由用户自带合法密钥；无密钥降级，数据源不混用且不绕过许可。",
+    }
+)
+
+
+class DataSourceCredentialService:
+    """协调受控数据源与系统钥匙串，公开接口只返回脱敏状态。"""
+
+    def __init__(self, credential_store: CredentialStore) -> None:
+        self._credential_store = credential_store
+        self._credential_references: dict[str, str] = {}
+        self._pending_revocations: dict[str, str] = {}
+
+    def configure(self, registration: CredentialRegistration) -> CredentialAuthorization:
+        """仅通过系统钥匙串配置 Finnhub，并返回不含引用的授权状态。"""
+
+        self._require_finnhub_credential_operation(registration.source_id)
+        if not isinstance(self._credential_store, KeyringCredentialStore):
+            raise ValueError("Finnhub 凭据必须使用系统钥匙串存储")
+
+        self._delete_existing_credential(registration.source_id)
+        self._credential_references[registration.source_id] = self._credential_store.put(
+            registration.source_id, registration.secret
+        )
+        return CredentialAuthorization(registration.source_id, is_authorized=True)
+
+    def revoke(self, source_id: str) -> CredentialAuthorization:
+        """仅撤销 Finnhub 的内部钥匙串引用并返回脱敏受限状态。"""
+
+        self._require_finnhub_credential_operation(source_id)
+        self._delete_existing_credential(source_id)
+        return CredentialAuthorization(source_id, is_authorized=False)
+
+    def retry_pending_revocation(self, source_id: str) -> CredentialAuthorization:
+        """重试删除失败的私有引用；重试期间公开状态始终保持受限。"""
+
+        self._require_finnhub_credential_operation(source_id)
+        reference = self._pending_revocations.get(source_id)
+        if reference is not None:
+            self._credential_store.delete(reference)
+            self._pending_revocations.pop(source_id, None)
+        return CredentialAuthorization(source_id, is_authorized=False)
+
+    def status(self, source_id: str) -> CredentialAuthorization:
+        """查询受控数据源的脱敏状态；未知数据源明确失败。"""
+
+        metadata = self._metadata_for(source_id)
+        if not metadata.requires_credentials:
+            return CredentialAuthorization(source_id, is_authorized=True)
+        return CredentialAuthorization(
+            source_id,
+            is_authorized=(
+                source_id in self._credential_references
+                and source_id not in self._pending_revocations
+            ),
+        )
+
+    def selection_record(self, source_id: str) -> DataSourceSelectionRecord:
+        """返回可审计的选择状态，永不携带凭据或钥匙串引用。"""
+
+        metadata = self._metadata_for(source_id)
+        access_state = metadata.access_state
+        if metadata.requires_credentials and self.status(source_id).is_authorized:
+            access_state = "已授权"
+
+        return DataSourceSelectionRecord(
+            source_id=metadata.source_id,
+            supported_markets=metadata.supported_markets,
+            requires_credentials=metadata.requires_credentials,
+            access_state=access_state,
+            degradation_notice=metadata.degradation_notice,
+            audit_note=_SELECTION_AUDIT_NOTES[source_id],
+        )
+
+    @staticmethod
+    def _metadata_for(source_id: str) -> DataSourceMetadata:
+        metadata = DATA_SOURCE_METADATA.get(source_id)
+        if metadata is None:
+            raise ValueError("不支持的数据源")
+        return metadata
+
+    def _require_finnhub_credential_operation(self, source_id: str) -> None:
+        self._metadata_for(source_id)
+        if source_id != "finnhub":
+            raise ValueError("仅 Finnhub 支持凭据操作")
+
+    def _delete_existing_credential(self, source_id: str) -> None:
+        """先保留删除失败的引用，确保后续仍可重试且不会继续授权。"""
+
+        reference = self._pending_revocations.get(source_id)
+        if reference is None:
+            reference = self._credential_references.pop(source_id, None)
+            if reference is not None:
+                self._pending_revocations[source_id] = reference
+        if reference is None:
+            return
+        self._credential_store.delete(reference)
+        self._pending_revocations.pop(source_id, None)
diff --git a/src/stock_agent/desktop/pages/data_source_page.py b/src/stock_agent/desktop/pages/data_source_page.py
new file mode 100644
index 0000000..997f7be
--- /dev/null
+++ b/src/stock_agent/desktop/pages/data_source_page.py
@@ -0,0 +1,24 @@
+"""定义数据源选择页面的安全状态模型。"""
+
+from dataclasses import dataclass
+
+from stock_agent.application.data_source_credential_service import DataSourceSelectionRecord
+
+
+@dataclass(frozen=True, slots=True)
+class DataSourcePageState:
+    """桌面端只从脱敏选择记录渲染数据源状态与摘要。"""
+
+    source_id: str
+    access_state: str
+    summary: str
+
+    @classmethod
+    def from_selection_record(cls, selection: DataSourceSelectionRecord) -> "DataSourcePageState":
+        """将不含敏感字段的选择记录转换为桌面摘要。"""
+
+        return cls(
+            source_id=selection.source_id,
+            access_state=selection.access_state,
+            summary=f"{selection.degradation_notice} {selection.audit_note}",
+        )
diff --git a/src/stock_agent/domain/freshness.py b/src/stock_agent/domain/freshness.py
new file mode 100644
index 0000000..b8d8bfd
--- /dev/null
+++ b/src/stock_agent/domain/freshness.py
@@ -0,0 +1,59 @@
+"""集中定义跨市场行情新鲜度的纯分类规则。"""
+
+from __future__ import annotations
+
+import math
+from datetime import datetime
+
+from stock_agent.contracts.common import FreshnessState
+from stock_agent.domain.market import Market
+
+
+class FreshnessClassificationError(ValueError):
+    """表示无法安全计算行情新鲜度的时间错误。"""
+
+
+def classify_freshness(
+    market: Market,
+    market_time: datetime,
+    collected_at: datetime,
+    is_open: bool,
+) -> FreshnessState:
+    """按市场时点、采集时点和开市状态返回兼容公共契约的新鲜度。"""
+
+    _validate_times(market_time, collected_at)
+
+    if not is_open:
+        return "CLOSED"
+
+    age_seconds = calculate_age_seconds(market_time, collected_at)
+    realtime_limit = 5 if market is Market.CN else 15
+    if age_seconds <= realtime_limit:
+        return "REALTIME"
+    if age_seconds <= 60:
+        return "NEAR_REALTIME"
+    if age_seconds <= 900:
+        return "DELAYED"
+    return "STALE"
+
+
+def _validate_times(market_time: datetime, collected_at: datetime) -> None:
+    """拒绝无时区或市场时点晚于采集时点的时间组合。"""
+
+    if not _is_aware(market_time) or not _is_aware(collected_at):
+        raise FreshnessClassificationError("市场时间和采集时间必须包含时区")
+    if market_time > collected_at:
+        raise FreshnessClassificationError("市场时间不能晚于采集时间")
+
+
+def calculate_age_seconds(market_time: datetime, collected_at: datetime) -> int:
+    """按真实时点差向上取整为秒，统一各行情路径的年龄口径。"""
+
+    _validate_times(market_time, collected_at)
+    return math.ceil((collected_at - market_time).total_seconds())
+
+
+def _is_aware(value: datetime) -> bool:
+    """返回时间是否带有可用 UTC 偏移。"""
+
+    return value.tzinfo is not None and value.utcoffset() is not None
diff --git a/tests/contract/test_data_source_credentials.py b/tests/contract/test_data_source_credentials.py
new file mode 100644
index 0000000..7da98a8
--- /dev/null
+++ b/tests/contract/test_data_source_credentials.py
@@ -0,0 +1,180 @@
+"""验证新浪和 Finnhub 的受控配置、公开状态与页面脱敏边界。"""
+
+import pytest
+
+
+class FakeKeyring:
+    """记录系统钥匙串调用，供受控配置路径验收使用。"""
+
+    def __init__(self) -> None:
+        self.items: dict[tuple[str, str], str] = {}
+        self.fail_next_write = False
+        self.fail_next_delete = False
+
+    def set_password(self, service_name: str, username: str, password: str) -> None:
+        if self.fail_next_write:
+            self.fail_next_write = False
+            raise RuntimeError("系统钥匙串写入失败")
+        self.items[(service_name, username)] = password
+
+    def delete_password(self, service_name: str, username: str) -> None:
+        if self.fail_next_delete:
+            self.fail_next_delete = False
+            raise RuntimeError("系统钥匙串删除失败")
+        self.items.pop((service_name, username))
+
+
+def test_公开授权状态不含密钥或钥匙串引用() -> None:
+    """普通调用方只能得到脱敏授权状态，不能读取内部钥匙串引用。"""
+
+    from stock_agent.application.data_source_credential_service import CredentialAuthorization
+
+    authorization = CredentialAuthorization(source_id="finnhub", is_authorized=True)
+
+    assert authorization.is_authorized is True
+    assert not hasattr(authorization, "secret")
+    assert not hasattr(authorization, "credential_reference")
+    assert "platform-keychain://" not in str(authorization)
+
+
+def test_新浪为公开只读候选且页面保持公开状态() -> None:
+    """新浪只能作为无需凭据的 A 股公开只读候选，不能承诺实时行情。"""
+
+    from stock_agent.adapters.platform.credential_store import ReferenceCredentialStore
+    from stock_agent.application.data_source_credential_service import (
+        DataSourceCredentialService,
+    )
+    from stock_agent.desktop.pages.data_source_page import DataSourcePageState
+
+    selection = DataSourceCredentialService(ReferenceCredentialStore()).selection_record("sina")
+    page_state = DataSourcePageState.from_selection_record(selection)
+
+    assert selection.source_id == "sina"
+    assert selection.supported_markets == ("CN",)
+    assert selection.requires_credentials is False
+    assert selection.access_state == "公开只读"
+    assert "不保证实时" in selection.degradation_notice
+    assert page_state.access_state == "公开只读"
+    assert "URL" in selection.audit_note
+    assert "市场时间" in selection.audit_note
+    assert "新鲜度" in selection.audit_note
+
+
+def test_finnhub仅通过系统钥匙串配置并在撤销后恢复受限() -> None:
+    """Finnhub 密钥必须进入 KeyringCredentialStore，公开状态和页面均不泄露引用。"""
+
+    from stock_agent.adapters.platform.credential_store import KeyringCredentialStore
+    from stock_agent.application.data_source_credential_service import (
+        CredentialRegistration,
+        DataSourceCredentialService,
+    )
+    from stock_agent.desktop.pages.data_source_page import DataSourcePageState
+
+    fake_keyring = FakeKeyring()
+    service = DataSourceCredentialService(KeyringCredentialStore(keyring_backend=fake_keyring))
+    assert service.status("finnhub").is_authorized is False
+    assert service.selection_record("finnhub").access_state == "受限"
+
+    configured = service.configure(CredentialRegistration("finnhub", "test-secret"))
+    page_state = DataSourcePageState.from_selection_record(service.selection_record("finnhub"))
+    assert configured.is_authorized is True
+    assert len(fake_keyring.items) == 1
+    assert page_state.access_state == "已授权"
+    assert "test-secret" not in page_state.summary
+    assert "platform-keychain://" not in page_state.summary
+    assert "platform-keychain://" not in str(configured)
+
+    revoked = service.revoke("finnhub")
+    assert revoked.is_authorized is False
+    assert fake_keyring.items == {}
+    assert service.selection_record("finnhub").access_state == "受限"
+
+
+def test_finnhub重配写入失败后公开状态恢复受限且不泄露引用() -> None:
+    """重配失败不能保留已删除凭据的陈旧引用或继续显示已授权。"""
+
+    from stock_agent.adapters.platform.credential_store import KeyringCredentialStore
+    from stock_agent.application.data_source_credential_service import (
+        CredentialRegistration,
+        DataSourceCredentialService,
+    )
+
+    fake_keyring = FakeKeyring()
+    service = DataSourceCredentialService(KeyringCredentialStore(keyring_backend=fake_keyring))
+    service.configure(CredentialRegistration("finnhub", "first-secret"))
+
+    fake_keyring.fail_next_write = True
+    with pytest.raises(RuntimeError, match="系统钥匙串写入失败"):
+        service.configure(CredentialRegistration("finnhub", "second-secret"))
+
+    authorization = service.status("finnhub")
+    selection = service.selection_record("finnhub")
+    assert authorization.is_authorized is False
+    assert selection.access_state == "受限"
+    assert fake_keyring.items == {}
+    assert "first-secret" not in str(authorization)
+    assert "second-secret" not in str(selection)
+    assert "platform-keychain://" not in str(authorization)
+    assert "platform-keychain://" not in str(selection)
+
+
+def test_finnhub撤销删除失败时保留内部重试并公开受限() -> None:
+    """删除失败时不能丢失私有引用；重试成功前公开面始终显示受限。"""
+
+    from stock_agent.adapters.platform.credential_store import KeyringCredentialStore
+    from stock_agent.application.data_source_credential_service import (
+        CredentialRegistration,
+        DataSourceCredentialService,
+    )
+
+    fake_keyring = FakeKeyring()
+    service = DataSourceCredentialService(KeyringCredentialStore(keyring_backend=fake_keyring))
+    service.configure(CredentialRegistration("finnhub", "test-secret"))
+    fake_keyring.fail_next_delete = True
+
+    with pytest.raises(RuntimeError, match="系统钥匙串删除失败"):
+        service.revoke("finnhub")
+
+    assert service.status("finnhub").is_authorized is False
+    assert service.selection_record("finnhub").access_state == "受限"
+    assert len(fake_keyring.items) == 1
+    assert "platform-keychain://" not in str(service.selection_record("finnhub"))
+
+    retried = service.retry_pending_revocation("finnhub")
+    assert retried.is_authorized is False
+    assert fake_keyring.items == {}
+
+
+def test_凭据操作拒绝非finnhub和非钥匙串存储() -> None:
+    """新浪、未知源及非系统钥匙串都不能创建、删除或伪造授权状态。"""
+
+    from stock_agent.adapters.platform.credential_store import ReferenceCredentialStore
+    from stock_agent.application.data_source_credential_service import (
+        CredentialRegistration,
+        DataSourceCredentialService,
+    )
+
+    service = DataSourceCredentialService(ReferenceCredentialStore())
+
+    with pytest.raises(ValueError):
+        service.configure(CredentialRegistration("sina", "test-secret"))
+    with pytest.raises(ValueError):
+        service.configure(CredentialRegistration("unknown", "test-secret"))
+    with pytest.raises(ValueError):
+        service.configure(CredentialRegistration("finnhub", "test-secret"))
+    with pytest.raises(ValueError):
+        service.revoke("sina")
+    with pytest.raises(ValueError):
+        service.revoke("unknown")
+    with pytest.raises(ValueError):
+        service.status("unknown")
+    with pytest.raises(ValueError):
+        service.selection_record("unknown")
+
+
+def test_页面只接受脱敏选择记录() -> None:
+    """页面不能从授权对象推断状态，避免密钥引用进入渲染路径。"""
+
+    from stock_agent.desktop.pages.data_source_page import DataSourcePageState
+
+    assert not hasattr(DataSourcePageState, "from_authorization")
diff --git a/tests/contract/test_market_data_contract.py b/tests/contract/test_market_data_contract.py
new file mode 100644
index 0000000..e4e9a82
--- /dev/null
+++ b/tests/contract/test_market_data_contract.py
@@ -0,0 +1,309 @@
+"""验证行情适配器协议与注册表不依赖具体供应商。"""
+
+from datetime import UTC, datetime, timedelta
+
+import pytest
+from pydantic import ValidationError
+
+from stock_agent.adapters.market_data.base import (
+    MarketDataAdapter,
+    NormalizedQuote,
+    SourceCapability,
+)
+from stock_agent.adapters.market_data.registry import (
+    DuplicateSourceError,
+    MarketDataRegistry,
+    SourceCapabilityViolationError,
+    UnknownSourceError,
+)
+from stock_agent.contracts.common import Freshness
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+def 市场证券身份(market: Market) -> InstrumentIdentity:
+    """构造仅用于契约测试的完整证券身份。"""
+
+    exchange, currency = {
+        Market.CN: ("SSE", "CNY"),
+        Market.HK: ("HKEX", "HKD"),
+        Market.US: ("NASDAQ", "USD"),
+    }[market]
+    return InstrumentIdentity(
+        market=market,
+        exchange=exchange,
+        display_code="600000",
+        currency=currency,
+    )
+
+
+class 演示行情适配器:
+    """用于验证注册表的最小适配器，不连接任何外部服务。"""
+
+    capability = SourceCapability(
+        source_id="演示来源",
+        markets=("CN",),
+        credential_required=False,
+        supports_realtime=True,
+    )
+
+    def fetch_quotes(self, codes: list[str], collected_at: datetime) -> list[NormalizedQuote]:
+        """返回空结果，避免测试引入供应商实现。"""
+
+        return []
+
+
+def test_注册表可以注册并按来源标识获取适配器() -> None:
+    """核心服务只通过通用协议和来源标识访问行情适配器。"""
+
+    registry = MarketDataRegistry()
+    adapter: MarketDataAdapter = 演示行情适配器()
+
+    registry.register(adapter)
+
+    assert registry.get("演示来源") is adapter
+
+
+def test_注册表拒绝重复来源标识() -> None:
+    """同一来源只能注册一次，避免运行时覆盖已选定的行情来源。"""
+
+    registry = MarketDataRegistry()
+    registry.register(演示行情适配器())
+
+    with pytest.raises(DuplicateSourceError, match="演示来源"):
+        registry.register(演示行情适配器())
+
+
+def test_注册表拒绝未知来源标识() -> None:
+    """请求未知来源时返回明确领域错误，而不是泄漏字典实现细节。"""
+
+    with pytest.raises(UnknownSourceError, match="未知来源"):
+        MarketDataRegistry().get("未知来源")
+
+
+@pytest.mark.parametrize(
+    ("field", "value"),
+    [
+        ("market_time", None),
+        ("collected_at", None),
+        ("data_version", ""),
+    ],
+)
+def test_规范化行情拒绝缺少关键时间或数据版本(field: str, value: datetime | str | None) -> None:
+    """缺少市场时间、采集时间或版本的供应商数据不能构造成统一行情。"""
+
+    quote = {
+        "security_id": 市场证券身份(Market.CN),
+        "price": 10.25,
+        "source_id": "演示来源",
+        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        "data_version": "演示版本-1",
+        "freshness": Freshness(state="REALTIME", age_seconds=1),
+    }
+    quote[field] = value
+
+    with pytest.raises(ValidationError):
+        NormalizedQuote(**quote)
+
+
+@pytest.mark.parametrize("field", ["market_time", "collected_at"])
+def test_规范化行情拒绝不带时区的时间(field: str) -> None:
+    """行情时间必须含时区，避免跨市场比较时把本地时间误认为同一时点。"""
+
+    quote = {
+        "security_id": 市场证券身份(Market.CN),
+        "price": 10.25,
+        "source_id": "演示来源",
+        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        "data_version": "演示版本-1",
+        "freshness": Freshness(state="REALTIME", age_seconds=1),
+    }
+    quote[field] = datetime(2026, 7, 14, 9, 30)
+
+    with pytest.raises(ValidationError):
+        NormalizedQuote(**quote)
+
+
+def test_规范化行情拒绝缺少单条行情新鲜度() -> None:
+    """每条行情必须带有新鲜度，供核心服务在使用前执行时效性控制。"""
+
+    with pytest.raises(ValidationError, match="freshness"):
+        NormalizedQuote(
+            security_id=市场证券身份(Market.CN),
+            price=10.25,
+            source_id="演示来源",
+            market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+            data_version="演示版本-1",
+        )
+
+
+def test_规范化行情接受严格的新鲜度状态() -> None:
+    """行情新鲜度使用现有公共契约，避免各来源自定义不兼容状态。"""
+
+    quote = NormalizedQuote(
+        security_id=市场证券身份(Market.CN),
+        price=10.25,
+        source_id="演示来源",
+        market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        data_version="演示版本-1",
+        freshness=Freshness(state="REALTIME", age_seconds=1),
+    )
+
+    assert quote.freshness.state == "REALTIME"
+
+
+def test_来源能力拒绝空市场范围() -> None:
+    """来源必须明确声明至少一个覆盖市场，避免注册不可用的适配器。"""
+
+    with pytest.raises(ValidationError, match="markets"):
+        SourceCapability(
+            source_id="演示来源",
+            markets=(),
+            credential_required=False,
+            supports_realtime=True,
+        )
+
+
+@pytest.mark.parametrize(
+    ("market", "age_seconds"),
+    [(Market.CN, 6), (Market.HK, 16), (Market.US, 16)],
+)
+def test_规范化行情拒绝超过市场实时年龄上限(market: Market, age_seconds: int) -> None:
+    """实时行情超过所属市场上限时，不能进入统一行情契约。"""
+
+    with pytest.raises(ValidationError, match="实时行情"):
+        NormalizedQuote(
+            security_id=市场证券身份(market),
+            price=10.25,
+            source_id="演示来源",
+            market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            collected_at=datetime(2026, 7, 14, 9, 30, age_seconds, tzinfo=UTC),
+            data_version="演示版本-1",
+            freshness=Freshness(state="REALTIME", age_seconds=age_seconds),
+        )
+
+
+@pytest.mark.parametrize(
+    ("market", "age_seconds"),
+    [(Market.CN, 5), (Market.HK, 15), (Market.US, 15)],
+)
+def test_规范化行情接受市场实时年龄上限内的行情(market: Market, age_seconds: int) -> None:
+    """实时行情等于所属市场上限时仍是合法可用的行情。"""
+
+    quote = NormalizedQuote(
+        security_id=市场证券身份(market),
+        price=10.25,
+        source_id="演示来源",
+        market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        collected_at=datetime(2026, 7, 14, 9, 30, age_seconds, tzinfo=UTC),
+        data_version="演示版本-1",
+        freshness=Freshness(state="REALTIME", age_seconds=age_seconds),
+    )
+
+    assert quote.freshness.age_seconds == age_seconds
+
+
+def test_规范化行情拒绝与时点计算不一致的新鲜度年龄() -> None:
+    """供应商不能把过期行情填成较小年龄以伪装为实时。"""
+
+    with pytest.raises(ValidationError, match="年龄"):
+        NormalizedQuote(
+            security_id=市场证券身份(Market.CN),
+            price=10.25,
+            source_id="演示来源",
+            market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            collected_at=datetime(2026, 7, 14, 9, 30, 6, tzinfo=UTC),
+            data_version="演示版本-1",
+            freshness=Freshness(state="REALTIME", age_seconds=1),
+        )
+
+
+@pytest.mark.parametrize(
+    ("age_seconds", "forged_state"),
+    [
+        (61, "NEAR_REALTIME"),
+        (901, "DELAYED"),
+        (3600, "NEAR_REALTIME"),
+    ],
+)
+def test_规范化行情拒绝非休市状态伪造的新鲜度状态(age_seconds: int, forged_state: str) -> None:
+    """非休市行情必须由真实市场时间严格推导状态，不能借低等级状态伪装延迟。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+
+    with pytest.raises(ValidationError, match="状态"):
+        NormalizedQuote(
+            security_id=市场证券身份(Market.CN),
+            price=10.25,
+            source_id="演示来源",
+            market_time=collected_at - timedelta(seconds=age_seconds),
+            collected_at=collected_at,
+            data_version="演示版本-1",
+            freshness=Freshness(state=forged_state, age_seconds=age_seconds),
+        )
+
+
+def test_规范化行情使用统一的向上取整年龄计算微秒时点() -> None:
+    """含微秒的采集间隔应统一向上取整，避免适配器与统一模型产生不同年龄。"""
+
+    market_time = datetime(2026, 7, 14, 9, 30, microsecond=123456, tzinfo=UTC)
+    quote = NormalizedQuote(
+        security_id=市场证券身份(Market.CN),
+        price=10.25,
+        source_id="演示来源",
+        market_time=market_time,
+        collected_at=market_time + timedelta(seconds=3, microseconds=1),
+        data_version="演示版本-1",
+        freshness=Freshness(state="REALTIME", age_seconds=4),
+    )
+
+    assert quote.freshness.age_seconds == 4
+
+
+def test_规范化行情拒绝未来市场时间() -> None:
+    """未来市场时间不能借由非实时状态绕过事实时点边界。"""
+
+    with pytest.raises(ValidationError, match="不能晚于"):
+        NormalizedQuote(
+            security_id=市场证券身份(Market.CN),
+            price=10.25,
+            source_id="演示来源",
+            market_time=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            data_version="演示版本-1",
+            freshness=Freshness(state="CLOSED", age_seconds=0),
+        )
+
+
+@pytest.mark.parametrize(
+    "returned_source, returned_market", [("其他来源", Market.CN), ("演示来源", Market.US)]
+)
+def test_注册表拒绝与所选来源能力不一致的整批行情(
+    returned_source: str, returned_market: Market
+) -> None:
+    """注册表必须拒绝来源或市场不一致的整批返回，不能泄露部分报价。"""
+
+    class 越界适配器(演示行情适配器):
+        def fetch_quotes(self, codes: list[str], collected_at: datetime) -> list[NormalizedQuote]:
+            return [
+                NormalizedQuote(
+                    security_id=市场证券身份(returned_market),
+                    price=10.25,
+                    source_id=returned_source,
+                    market_time=collected_at,
+                    collected_at=collected_at,
+                    data_version="演示版本-1",
+                    freshness=Freshness(state="REALTIME", age_seconds=0),
+                )
+            ]
+
+    registry = MarketDataRegistry()
+    registry.register(越界适配器())
+
+    with pytest.raises(SourceCapabilityViolationError):
+        registry.fetch_quotes(
+            "演示来源", ["600000"], datetime(2026, 7, 14, 9, 30, tzinfo=UTC), Market.CN
+        )
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
new file mode 100644
index 0000000..8738db4
--- /dev/null
+++ b/tests/failure/test_market_data_failures.py
@@ -0,0 +1,108 @@
+"""验证新浪代码规则拒绝不安全或不受支持的身份。"""
+
+from datetime import UTC, datetime
+from pathlib import Path
+
+import pytest
+
+from stock_agent.adapters.market_data.sina_adapter import SinaDataSourceError, SinaHttpAdapter
+from stock_agent.adapters.market_data.sina_codes import (
+    UnsupportedSinaCodeError,
+    normalize_sina_code,
+)
+from stock_agent.application.versioning_service import VersioningService
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+class 忽略事实记录器:
+    """隔离响应校验测试的记录端口，不替代持久化集成测试。"""
+
+    def record(self, raw_response: bytes, quotes: list[object]) -> None:
+        """响应校验失败路径不会调用该端口。"""
+
+
+def 新浪响应(日期: str, 时间: str) -> bytes:
+    """构造字段数量完整的单条新浪响应，供失败边界覆盖使用。"""
+
+    fields = ["浦发银行", "10.00", "10.10", "10.25", *("0" for _ in range(26)), 日期, 时间, "00"]
+    return f'var hq_str_sh600000="{",".join(fields)}";'.encode("gbk")
+
+
+@pytest.mark.parametrize(
+    ("exchange", "display_code", "expected"),
+    [("SSE", "600000", "sh600000"), ("SZSE", "000001", "sz000001")],
+)
+def test_新浪代码规范化支持沪深交易所(exchange: str, display_code: str, expected: str) -> None:
+    """新浪 A 股请求代码必须携带正确交易所前缀。"""
+
+    identity = InstrumentIdentity(Market.CN, exchange, display_code, "CNY")
+
+    assert normalize_sina_code(identity) == expected
+
+
+@pytest.mark.parametrize(
+    "identity",
+    [
+        InstrumentIdentity(Market.HK, "HKEX", "00001", "HKD"),
+        InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD"),
+        InstrumentIdentity(Market.CN, "BSE", "830000", "CNY"),
+        InstrumentIdentity(Market.CN, "SSE", "60000", "CNY"),
+        InstrumentIdentity(Market.CN, "SZSE", "0000A1", "CNY"),
+        InstrumentIdentity(Market.CN, "SSE", "１２３４５６", "CNY"),
+    ],
+)
+def test_新浪代码规范化拒绝跨市场交易所和非法代码(
+    identity: InstrumentIdentity,
+) -> None:
+    """非中国市场、非沪深交易所或非六码数字代码一律拒绝。"""
+
+    with pytest.raises(UnsupportedSinaCodeError):
+        normalize_sina_code(identity)
+
+
+@pytest.mark.parametrize("codes", [[], ["600000"], ["sh60000"], ["xx600000"], ["sh６０００００"]])
+def test_新浪适配器拒绝空或非法请求代码(codes: list[str], local_data_root: Path) -> None:
+    """请求代码必须已是沪深前缀加六码 ASCII 数字，避免构造越界地址。"""
+
+    with pytest.raises(SinaDataSourceError):
+        SinaHttpAdapter(
+            lambda _url: b"", 忽略事实记录器(), VersioningService(local_data_root)
+        ).fetch_quotes(codes, datetime.now(UTC))
+
+
+@pytest.mark.parametrize(
+    "response",
+    [
+        RuntimeError("网络故障"),
+        b"\xff",
+        'var hq_str_sh600000="浦发银行,10.00";'.encode("gbk"),
+        'var hq_str_sh600000="浦发银行,abc,10.10,无效";'.encode("gbk"),
+        新浪响应("2026-02-30", "09:30:00"),
+        新浪响应("2026-07-14", "25:30:00"),
+    ],
+)
+def test_新浪适配器拒绝异常或不完整响应且不返回部分行情(
+    response: bytes | Exception, local_data_root: Path
+) -> None:
+    """读取、解码、字段和市场时间任一异常都必须作为数据源错误整体失败。"""
+
+    def 读取行情(_url: str) -> bytes:
+        if isinstance(response, Exception):
+            raise response
+        return response
+
+    with pytest.raises(SinaDataSourceError):
+        SinaHttpAdapter(
+            读取行情, 忽略事实记录器(), VersioningService(local_data_root)
+        ).fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, tzinfo=UTC))
+
+
+def test_新浪适配器响应缺少任一请求代码时拒绝全部行情(local_data_root: Path) -> None:
+    """多证券响应缺行时不能泄露已成功解析的部分结果。"""
+
+    response = 新浪响应("2026-07-14", "09:30:00")
+
+    with pytest.raises(SinaDataSourceError):
+        SinaHttpAdapter(
+            lambda _url: response, 忽略事实记录器(), VersioningService(local_data_root)
+        ).fetch_quotes(["sh600000", "sz000001"], datetime(2026, 7, 14, 1, 30, tzinfo=UTC))
diff --git a/tests/integration/test_sina_market_data_provenance.py b/tests/integration/test_sina_market_data_provenance.py
new file mode 100644
index 0000000..db15db0
--- /dev/null
+++ b/tests/integration/test_sina_market_data_provenance.py
@@ -0,0 +1,206 @@
+"""验证新浪原始响应与规范化行情都追加保存到本地事实链。"""
+
+from datetime import UTC, datetime
+from pathlib import Path
+
+import pytest
+
+from stock_agent.adapters.market_data.sina_adapter import (
+    SinaDataSourceError,
+    SinaHttpAdapter,
+    SinaPersistenceProof,
+)
+from stock_agent.adapters.market_data.sina_provenance import SinaMarketDataFactRecorder
+from stock_agent.application.versioning_service import VersioningService
+
+
+def 新浪响应() -> bytes:
+    """构造一条与新浪公开格式一致的 GBK 响应。"""
+
+    return (
+        'var hq_str_sh600000="浦发银行,10.00,10.10,10.25,10.30,9.90,10.24,10.25,100,1000,'
+        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";'
+    ).encode("gbk")
+
+
+def test_新浪响应和规范化结果以同一版本关联追加保存(local_data_root: Path) -> None:
+    """原始字节与规范化结果必须各有不可变工件，并由版本和哈希关联。"""
+
+    service = VersioningService(local_data_root)
+    adapter = SinaHttpAdapter(
+        lambda _url: 新浪响应(),
+        fact_recorder=SinaMarketDataFactRecorder(service),
+        versioning_service=service,
+    )
+    collected_at = datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC)
+
+    quotes = adapter.fetch_quotes(["sh600000"], collected_at)
+
+    raw_versions = list((local_data_root / "artifacts" / "market-data-raw").iterdir())
+    normalized_versions = list((local_data_root / "artifacts" / "market-data-normalized").iterdir())
+    assert len(raw_versions) == len(normalized_versions) == 1
+    normalized = service.read_bytes("market-data-normalized", normalized_versions[0].name)
+    assert quotes[0].data_version.encode() in normalized
+    assert b'"source_id":"sina"' in normalized
+    assert b'"market_time"' in normalized
+    assert b'"collected_at"' in normalized
+    assert (
+        service.metadata_for("market-data-normalized", normalized_versions[0].name)[
+            "parent_version_id"
+        ]
+        == raw_versions[0].name
+    )
+
+
+def test_新浪事实保存失败时不返回未持久化行情(local_data_root: Path) -> None:
+    """事实链提交失败必须使整批读取失败，不能把内存结果冒充事实。"""
+
+    class 失败记录器:
+        def record(self, raw_response: bytes, quotes: list[object]) -> None:
+            raise RuntimeError("本地保存失败")
+
+    adapter = SinaHttpAdapter(
+        lambda _url: 新浪响应(),
+        fact_recorder=失败记录器(),
+        versioning_service=VersioningService(local_data_root),
+    )
+
+    with pytest.raises(SinaDataSourceError, match="保存"):
+        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))
+
+
+def test_新浪适配器拒绝形态正确但未真实落盘的持久化证明(local_data_root: Path) -> None:
+    """即使证明字段和原始响应哈希均正确，缺少真实工件也必须整批失败。"""
+
+    raw_response = 新浪响应()
+    proof = SinaPersistenceProof(
+        raw_artifact_version_id="raw-1",
+        normalized_artifact_version_id="normalized-1",
+        parent_version_id="raw-1",
+    )
+
+    class 空记录器:
+        def record(self, raw_response: bytes, quotes: list[object]) -> SinaPersistenceProof:
+            return proof
+
+    adapter = SinaHttpAdapter(
+        lambda _url: raw_response,
+        fact_recorder=空记录器(),
+        versioning_service=VersioningService(local_data_root),
+    )
+
+    with pytest.raises(SinaDataSourceError, match="工件"):
+        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))
+
+
+def test_新浪适配器拒绝父版本关联不匹配的真实工件(local_data_root: Path) -> None:
+    """真实落盘后仍必须回读校验父版本关联。"""
+
+    service = VersioningService(local_data_root)
+
+    class 篡改证明记录器:
+        def record(self, raw_response: bytes, normalized_content: bytes) -> SinaPersistenceProof:
+            raw = service.commit_bytes(
+                dataset="market-data-raw",
+                version_id="raw-1",
+                content=raw_response,
+                source_id="sina",
+            )
+            normalized = service.commit_bytes(
+                dataset="market-data-normalized",
+                version_id="normalized-1",
+                content=normalized_content,
+                source_id="sina",
+                parent_version_id="other-raw",
+            )
+            return SinaPersistenceProof(
+                raw_artifact_version_id=raw.version_id,
+                normalized_artifact_version_id=normalized.version_id,
+                parent_version_id=raw.version_id,
+            )
+
+    adapter = SinaHttpAdapter(
+        lambda _url: 新浪响应(),
+        fact_recorder=篡改证明记录器(),
+        versioning_service=service,
+    )
+
+    with pytest.raises(SinaDataSourceError, match="工件"):
+        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))
+
+
+@pytest.mark.parametrize(
+    "proof",
+    [
+        None,
+        SinaPersistenceProof(
+            raw_artifact_version_id="raw-1",
+            normalized_artifact_version_id="normalized-1",
+            parent_version_id="other-raw",
+        ),
+    ],
+)
+def test_新浪适配器拒绝缺失或不完整的持久化证明(
+    proof: SinaPersistenceProof | None, local_data_root: Path
+) -> None:
+    """公共适配器不能信任空记录器；原始与规范化工件证明必须完整关联。"""
+
+    class 返回证明的记录器:
+        def record(
+            self, raw_response: bytes, normalized_content: bytes
+        ) -> SinaPersistenceProof | None:
+            return proof
+
+    adapter = SinaHttpAdapter(
+        lambda _url: 新浪响应(),
+        fact_recorder=返回证明的记录器(),
+        versioning_service=VersioningService(local_data_root),
+    )
+
+    with pytest.raises(SinaDataSourceError, match="证明"):
+        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))
+
+
+@pytest.mark.parametrize(
+    "normalized_content",
+    [
+        b'{"source_id":"sina","quotes":[]}',
+        b'{"source_id":"sina","quotes":[{"price":1.0}]}',
+    ],
+)
+def test_新浪适配器拒绝父链正确但不属于当前报价批次的规范化工件(
+    normalized_content: bytes, local_data_root: Path
+) -> None:
+    """规范化工件必须精确承载本次适配器生成的完整报价批次。"""
+
+    service = VersioningService(local_data_root)
+
+    class 写入旧批次的记录器:
+        def record(self, raw_response: bytes, normalized_payload: bytes) -> SinaPersistenceProof:
+            raw = service.commit_bytes(
+                dataset="market-data-raw",
+                version_id="raw-1",
+                content=raw_response,
+                source_id="sina",
+            )
+            normalized = service.commit_bytes(
+                dataset="market-data-normalized",
+                version_id="normalized-1",
+                content=normalized_content,
+                source_id="sina",
+                parent_version_id=raw.version_id,
+            )
+            return SinaPersistenceProof(
+                raw_artifact_version_id=raw.version_id,
+                normalized_artifact_version_id=normalized.version_id,
+                parent_version_id=raw.version_id,
+            )
+
+    adapter = SinaHttpAdapter(
+        lambda _url: 新浪响应(),
+        fact_recorder=写入旧批次的记录器(),
+        versioning_service=service,
+    )
+
+    with pytest.raises(SinaDataSourceError, match="规范化"):
+        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))
diff --git a/tests/integration/test_single_market_daily_pipeline.py b/tests/integration/test_single_market_daily_pipeline.py
new file mode 100644
index 0000000..9274d3a
--- /dev/null
+++ b/tests/integration/test_single_market_daily_pipeline.py
@@ -0,0 +1,46 @@
+"""验证新浪 A 股行情适配器的受控请求与规范化输出。"""
+
+from datetime import UTC, datetime
+from pathlib import Path
+
+from stock_agent.adapters.market_data.sina_adapter import SinaHttpAdapter
+from stock_agent.adapters.market_data.sina_provenance import SinaMarketDataFactRecorder
+from stock_agent.application.versioning_service import VersioningService
+from stock_agent.domain.market import Market
+
+
+def test_新浪适配器以精确地址读取_GBK_行情并保留完整溯源信息(local_data_root: Path) -> None:
+    """适配器只能使用约定地址，并将合法响应转为可量化使用的完整行情。"""
+
+    requested_urls: list[str] = []
+    response = (
+        'var hq_str_sh600000="浦发银行,10.00,10.10,10.25,10.30,9.90,10.24,10.25,100,1000,'
+        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";\n'
+        'var hq_str_sz000001="平安银行,12.00,12.10,12.25,12.30,11.90,12.24,12.25,100,1000,'
+        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";'
+    ).encode("gbk")
+
+    def 读取行情(url: str) -> bytes:
+        requested_urls.append(url)
+        return response
+
+    collected_at = datetime(2026, 7, 14, 1, 30, 3, 1, tzinfo=UTC)
+
+    service = VersioningService(local_data_root)
+    quotes = SinaHttpAdapter(
+        读取行情,
+        SinaMarketDataFactRecorder(service),
+        service,
+    ).fetch_quotes(["sh600000", "sz000001"], collected_at)
+
+    assert requested_urls == ["http://hq.sinajs.cn/list=sh600000,sz000001"]
+    assert [quote.price for quote in quotes] == [10.25, 12.25]
+    assert [quote.security_id.display_code for quote in quotes] == ["600000", "000001"]
+    assert [quote.security_id.exchange for quote in quotes] == ["SSE", "SZSE"]
+    assert all(quote.security_id.market is Market.CN for quote in quotes)
+    assert all(quote.source_id == "sina" for quote in quotes)
+    assert all(quote.market_time.tzinfo is not None for quote in quotes)
+    assert all(quote.market_time.tzinfo.key == "Asia/Shanghai" for quote in quotes)
+    assert all(quote.data_version.startswith("sina-") for quote in quotes)
+    assert all(quote.freshness.state == "REALTIME" for quote in quotes)
+    assert all(quote.freshness.age_seconds == 4 for quote in quotes)
diff --git a/tests/property/test_freshness_rules.py b/tests/property/test_freshness_rules.py
new file mode 100644
index 0000000..51c79de
--- /dev/null
+++ b/tests/property/test_freshness_rules.py
@@ -0,0 +1,97 @@
+"""验证跨市场行情新鲜度的纯规则边界。"""
+
+from datetime import UTC, datetime, timedelta
+
+import pytest
+
+from stock_agent.domain.freshness import FreshnessClassificationError, classify_freshness
+from stock_agent.domain.market import Market
+
+
+@pytest.mark.parametrize(
+    ("market", "realtime_limit"),
+    [
+        (Market.CN, 0),
+        (Market.HK, 0),
+        (Market.US, 0),
+        (Market.CN, 5),
+        (Market.HK, 15),
+        (Market.US, 15),
+    ],
+)
+def test_交易时段在各市场实时精确边界内为实时(market: Market, realtime_limit: int) -> None:
+    """各市场年龄等于实时阈值时仍应判为实时行情。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    market_time = collected_at - timedelta(seconds=realtime_limit)
+
+    assert classify_freshness(market, market_time, collected_at, is_open=True) == "REALTIME"
+
+
+@pytest.mark.parametrize(
+    ("market", "age_seconds"),
+    [(Market.CN, 6), (Market.HK, 16), (Market.US, 16)],
+)
+def test_交易时段超过各市场实时边界为近实时(market: Market, age_seconds: int) -> None:
+    """实时阈值之外且不超过一分钟的行情应降为近实时。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    market_time = collected_at - timedelta(seconds=age_seconds)
+
+    assert classify_freshness(market, market_time, collected_at, is_open=True) == "NEAR_REALTIME"
+
+
+@pytest.mark.parametrize(
+    ("age_seconds", "expected"),
+    [(60, "NEAR_REALTIME"), (61, "DELAYED"), (900, "DELAYED"), (901, "STALE")],
+)
+def test_交易时段通用时效边界(age_seconds: int, expected: str) -> None:
+    """一分钟与十五分钟边界必须保持与公共新鲜度契约一致。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    market_time = collected_at - timedelta(seconds=age_seconds)
+
+    assert classify_freshness(Market.CN, market_time, collected_at, is_open=True) == expected
+
+
+def test_休市时忽略时间年龄并返回休市() -> None:
+    """休市行情不能被标为可实时使用。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+
+    assert (
+        classify_freshness(Market.US, collected_at - timedelta(days=1), collected_at, is_open=False)
+        == "CLOSED"
+    )
+
+
+def test_休市时未来市场时间仍被拒绝() -> None:
+    """未来市场时间无论开闭市都不能绕过时间一致性校验。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+
+    with pytest.raises(FreshnessClassificationError):
+        classify_freshness(
+            Market.CN, collected_at + timedelta(seconds=1), collected_at, is_open=False
+        )
+
+
+@pytest.mark.parametrize(
+    ("market_time", "collected_at"),
+    [
+        (datetime(2026, 7, 14, 9, 30), datetime(2026, 7, 14, 9, 30, tzinfo=UTC)),
+        (
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            datetime(2026, 7, 14, 9, 30),
+        ),
+        (
+            datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        ),
+    ],
+)
+def test_拒绝无时区或负年龄的时间(market_time: datetime, collected_at: datetime) -> None:
+    """无时区和未来市场时间都不能伪装成新鲜行情。"""
+
+    with pytest.raises(FreshnessClassificationError):
+        classify_freshness(Market.CN, market_time, collected_at, is_open=True)

```

