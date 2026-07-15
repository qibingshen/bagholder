# Task 1 行情适配器协议与注册表报告

## 涉及文件

- 新增 `src/stock_agent/adapters/market_data/base.py`：供应商无关的能力描述、规范化行情模型和适配器协议。
- 新增 `src/stock_agent/adapters/market_data/registry.py`：适配器注册、重复来源与未知来源领域错误。
- 新增 `src/stock_agent/adapters/market_data/__init__.py`：公共接口导出。
- 新增 `tests/contract/test_market_data_contract.py`：协议和注册表契约测试。

## 失败测试证据

在实现前运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
```

结果：收集阶段失败，错误为 `ModuleNotFoundError: No module named 'stock_agent.adapters.market_data'`。这证明新增测试在协议和注册表尚未实现时不能通过。

## 通过验证

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
```

结果：`8 passed in 0.73s`。

```powershell
py -3.12 -m ruff format --check src tests
```

结果：`49 files already formatted`。

```powershell
py -3.12 -m ruff check src tests
```

结果：`All checks passed!`。

另行执行 `git diff --check`，无输出且退出成功。

## 提交

- 提交哈希：`525490b97d61ae20d0ce6e6949180c479ff9f85f`
- 提交信息：`feat: add market data adapter registry`

## 自检结论

- `SourceCapability` 提供来源标识、市场、凭据要求和实时能力。
- `NormalizedQuote` 提供证券身份、价格、来源、市场时间、采集时间和非空数据版本；两个时间字段均拒绝无时区值。
- `MarketDataAdapter` 仅暴露 `capability` 与 `fetch_quotes(codes, collected_at)`，不包含 HTTP、供应商解析或持久化逻辑。
- 注册表可注册并获取适配器，重复来源抛出 `DuplicateSourceError`，未知来源抛出 `UnknownSourceError`。
- 代码、注释、文档字符串和测试说明均为简体中文。

## 未解决问题

无。

## 复核修复（行情新鲜度）

### 修改文件

- 修改 `src/stock_agent/adapters/market_data/base.py`：`NormalizedQuote` 必填使用公共 `Freshness` 契约；`SourceCapability.markets` 限制为非空。
- 修改 `tests/contract/test_market_data_contract.py`：新增缺少行情新鲜度的拒绝测试、严格新鲜度类型测试和空市场范围拒绝测试，并为既有行情样例补齐新鲜度。

### 失败测试证据

新增测试后、修复前运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
```

结果：`3 failed, 8 passed`。失败原因分别为：缺少 `freshness` 时未抛出 `ValidationError`、传入 `freshness` 后模型没有该属性、空 `markets` 时未抛出 `ValidationError`。

### 通过验证

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
```

结果：`11 passed in 0.56s`。

```powershell
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

结果：分别为 `49 files already formatted` 和 `All checks passed!`。另行执行 `git diff --check`，无输出且退出成功。

### 新提交

- 提交哈希：`f0415b7c90119f25204e83b4162e8df5a294f9b2`
- 提交信息：`fix: require quote freshness`

### 复核自检与未解决问题

- 单条 `NormalizedQuote` 现强制携带现有公共 `Freshness` 类型，且不新增供应商 HTTP、新鲜度计算或交易能力。
- `SourceCapability` 现拒绝空市场范围。
- 未解决问题：无。

## v3 复核补充（HK 实时年龄边界）

### 修改文件

- 修改 `tests/contract/test_market_data_contract.py`：REALTIME 年龄参数化测试新增 `Market.HK` 的 16 秒拒绝与 15 秒通过边界。

### 新增测试验证证据

新增 HK 用例后、未改动实现即运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v -k 'HK'
```

结果：`2 passed, 15 deselected in 0.48s`。现有实现已为 HK 配置 15 秒上限，因此本次为测试覆盖补充，不需要生产代码修复。

### 通过验证

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
```

结果：`17 passed in 0.49s`。

```powershell
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

结果：分别为 `49 files already formatted` 和 `All checks passed!`。另行执行 `git diff --check`，无输出且退出成功。

### 新提交

- 提交哈希：`161ffa066b68bf86457011a5c0f20993230e86f4`
- 提交信息：`test: cover hk quote freshness boundary`

### 复核自检与未解决问题

- 未改动行情协议实现，也未引入 HTTP、供应商解析、交易或其他范围外能力。
- 未解决问题：无。

## 二次复核修复（按市场限制实时年龄）

### 修改文件

- 修改 `src/stock_agent/adapters/market_data/base.py`：将 `NormalizedQuote.security_id` 收敛为现有 `InstrumentIdentity`，并依据 `security_id.market` 校验实时行情年龄。CN 上限为 5 秒，HK/US 上限为 15 秒。
- 修改 `tests/contract/test_market_data_contract.py`：新增 CN 6 秒和 US 16 秒实时行情拒绝测试，以及 CN 5 秒和 US 15 秒边界通过测试；既有样例改为使用完整证券身份。

### 失败测试证据

新增测试后、修复前运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
```

结果：`4 failed, 11 passed`。失败原因是 `NormalizedQuote.security_id` 当时仅接受字符串，不能承载 `security_id.market`，因此无法执行市场实时年龄校验；CN 6 秒、US 16 秒拒绝测试与边界通过测试均未满足。

### 通过验证

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
```

结果：`15 passed in 0.45s`。

```powershell
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

结果：分别为 `49 files already formatted` 和 `All checks passed!`。另行执行 `git diff --check`，无输出且退出成功。

### 新提交

- 提交哈希：`d7b0a4c44660222f3d9c5f90437cb4e6588cfca1`
- 提交信息：`fix: validate quote freshness by market`

### 复核自检与未解决问题

- 仅实施模型层契约校验；未实现 HTTP、供应商解析、新鲜度计算或交易能力。
- `market_time` 与 `collected_at` 仍为必填且须带时区；Pydantic 对不可解析的时间输入会拒绝构造。
- 未解决问题：无。
