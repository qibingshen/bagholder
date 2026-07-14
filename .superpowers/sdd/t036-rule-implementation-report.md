# T036 后续市场规则实现报告

## 实现说明

- 保留 `is_usable_for_current_prediction` 的布尔返回契约；新增
  `require_usable_for_current_prediction` 作为强制准入入口。该入口会对延迟、过期、休市、未知状态和时点不可验证的行情抛出
  `FreshnessClassificationError`，并给出中文拒绝原因。
- `CompanyAction` 增加可选的 `adjustment_ratio`、`security_id` 与 `market`，保持既有构造调用兼容；已校验复权比例为有限正数、有效时间带时区、证券身份与市场一致。
- 新增 `require_company_actions_for_adjustment`。复权历史研究缺少公司行动记录时抛出
  `PointInTimeViolation`，不会生成或猜测公司行动。
- 失败用例改为调用严格准入入口，保留既有布尔接口的 T041 契约测试。

## TDD 红灯证据

先执行：

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -v
```

结果为 `42 passed, 9 failed`。失败分别来自当前预测无法给出领域拒绝原因、公司行动新增字段缺失，以及
`require_company_actions_for_adjustment` 不可导入，符合本任务的预期红灯范围。

## 绿灯与质量验证

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -v
py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/property/test_point_in_time_integrity.py -v
py -3.12 -m ruff format --check src/stock_agent/domain/freshness.py src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py
py -3.12 -m ruff check src/stock_agent/domain/freshness.py src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py
py -3.12 tools/check_chinese_project_text.py src/stock_agent/domain
```

- 失败用例：`51 passed`。
- 新鲜度与公司行动相关属性测试：`71 passed`。
- 改动范围 Ruff 格式与静态检查均通过。
- 改动范围中文检查通过。

## 仓库级验证与回滚

- 全量 pytest 结果为 `338 passed, 1 failed`；失败为既有
  `tests/property/test_market_rules.py::test_证券代码跨市场必须不同身份`，它构造六位港股代码，已被现有五位港股代码规则拒绝，与本任务改动无关。
- 全仓 Ruff 格式检查仍报告既有 `src/stock_agent/desktop/pages/_recovery.py` 与
  `tests/property/test_freshness_rules.py` 需要格式化；全仓 Ruff 静态检查在本任务改动后未报告新增问题。
- 全仓中文检查仍报告既有 `tests/failure/test_market_data_failures.py:88` 的类型忽略注释缺少中文说明；本任务新增文字均为简体中文。
- 如需回滚，仅回退本任务提交即可；无外部数据、预测数值、券商或交易副作用。
