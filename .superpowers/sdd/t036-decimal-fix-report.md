# T036 公司行动复权比例 Decimal 兼容修复报告

## 修复范围

- `CompanyAction.adjustment_ratio` 明确接受有限且大于零的 `int`、`float` 与
  `Decimal`，并将类型注解同步为这三类数值。
- 校验不再依赖 `numbers.Real`；该抽象不会将 `Decimal` 视为实数，导致合法精确比例被误拒。
- `bool` 保持显式拒绝，字符串、复数、非有限值、零和负数均继续统一以中文 `ValueError` 拒绝。
- 本次只变更领域模型和测试，未访问网络、未生成预测、未发起交易。

## TDD 证据

先新增 `Decimal("1.1")` 可接受的失败用例，并执行：

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k decimal -v
```

实现前得到 `1 failed, 63 deselected`：`Decimal("1.1")` 因未通过 `Real` 类型判断而被拒绝。

随后以显式类型白名单完成最小实现，失败用例文件复验为 `64 passed`。拒绝覆盖保留并扩展为：

- `True`、`False`
- 字符串和复数
- `float("nan")`、`float("inf")`
- `Decimal("NaN")`、`Decimal("Infinity")`
- 整数与 `Decimal` 的零及负数

## 验证结果

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py tests/property/test_point_in_time_integrity.py -v
py -3.12 -m ruff format --check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
py -3.12 -m ruff check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
py -3.12 tools/check_chinese_project_text.py src/stock_agent/domain tests/failure/test_market_data_failures.py
```

- Pytest：`69 passed`。
- Ruff 格式检查：4 个文件均已格式化。
- Ruff 静态检查：通过。
- 简体中文检查：通过。

## 风险与回滚

- 允许 `Decimal` 后，调用方可保留十进制比例精度；领域对象不会把它转换为 `float`。
- 可接受类型仅限 `int`、`float`、`Decimal`，不会因泛化数值协议而放宽至自定义数值或复数。
- 如需回滚，仅回退本次提交即可；该提交没有外部副作用。
