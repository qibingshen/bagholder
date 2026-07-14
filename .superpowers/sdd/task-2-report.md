# Task 2 完成报告：新鲜度与新浪代码规则

## 范围与文件

- `src/stock_agent/domain/freshness.py`：跨市场新鲜度纯分类规则。
- `src/stock_agent/adapters/market_data/sina_codes.py`：新浪 A 股请求代码纯规范化规则。
- `tests/property/test_freshness_rules.py`：新鲜度阈值、休市和时间错误测试。
- `tests/failure/test_market_data_failures.py`：新浪代码合法映射与拒绝测试。

未实现 HTTP、供应商响应解析、存储、凭据、券商、下单或自动交易功能。

## TDD 证据

1. 先新增两份测试文件并执行指定 pytest 命令。
2. 初次执行在收集阶段失败：`ModuleNotFoundError`，缺少
   `stock_agent.domain.freshness` 与
   `stock_agent.adapters.market_data.sina_codes`，证明测试先于实现存在。
3. 写入最小纯规则实现后，补充“休市时优先返回 `CLOSED`”测试；该测试先因
   `FreshnessClassificationError` 失败，再将休市分支移动到时间校验之前。
4. 最终指定测试全部通过。

## 验证证据

执行时间：2026-07-14。

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py -v
```

结果：`21 passed in 0.67s`。

```powershell
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

结果：格式检查显示 `53 files already formatted`，静态检查退出码为 0 且无诊断。

## 自检

- CN 在 5 秒、HK/US 在 15 秒仍为 `REALTIME`，超限为 `NEAR_REALTIME`。
- 60 秒为 `NEAR_REALTIME`，61 秒至 900 秒为 `DELAYED`，901 秒为 `STALE`。
- 休市一律为 `CLOSED`；开市时无时区与负年龄均抛出领域错误。
- 仅 CN 的 SSE/SZSE 六位数字代码映射为 `sh`/`sz` 前缀；其他市场、交易所和代码均拒绝。
- 已执行暂存差异空白检查，任务实现提交未包含范围外文件。

## 提交哈希

- `29ecc09863bb448f10e8acc262f805d8dc0973e9`：`feat: enforce freshness and sina code rules`

## Concerns

- 无已知功能性 concern。
- 工作区中存在其他代理或用户的未跟踪、已修改文件；本任务提交未包含它们。

## 复核修复记录

### 修复内容

- 新浪代码六位校验改为逐字符严格 ASCII `0-9` 判断，不再接受 Unicode 十进制数字。
- 新鲜度测试补充 CN/HK/US 开市时年龄为 0 秒的 `REALTIME` 边界。
- 新鲜度测试补充 `collected_at` 无时区时必须拒绝的场景。
- 新浪代码拒绝测试补充全角数字 `１２３４５６`。

### 复核 TDD 证据

新增全角数字拒绝用例后，指定 pytest 命令先失败：该用例未抛出
`UnsupportedSinaCodeError`，原因是原实现使用 `isdecimal()` 接受全角数字。收紧
ASCII 校验后，指定 pytest 命令通过。

### 复核验证证据

执行时间：2026-07-14。

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py -v
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

结果：`26 passed in 0.58s`；格式检查显示 `53 files already formatted`；静态检查退出码为
0 且无诊断。
