# T036 Decimal 复权比例有限性修复报告

## 修复范围

- `CompanyAction.adjustment_ratio` 对 `Decimal` 使用 `is_finite()` 判断有限性，随后仅接受大于零的值；不再将 `Decimal` 转换为 `float`。
- `float` 保持使用 `math.isfinite()`；非布尔 `int` 直接按正值判断；`bool`、其他类型、非有限值、零和负值统一抛出 `ValueError`。
- 未修改证券与市场身份绑定、公司行动缺失阻断或其他市场规则；未访问网络、未生成预测、未发起交易。

## TDD 证据

先新增极大但有限的 `Decimal("1E+999999")` 接受用例，以及 `Decimal("-Infinity")`、`Decimal("sNaN")` 拒绝用例；实现前运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k '极大但有限的_decimal' -v
```

结果为 `1 failed, 66 deselected`：极大有限 Decimal 被原有 `math.isfinite()` 路径错误拒绝。完成按类型的最小校验实现后，Decimal 相关用例运行结果为 `16 passed, 51 deselected`。

## 验证结果

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py tests/property/test_point_in_time_integrity.py -v
py -3.12 -m ruff format --check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
py -3.12 -m ruff check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
py -3.12 tools/check_chinese_project_text.py src/stock_agent/domain tests/failure/test_market_data_failures.py
```

- Pytest：`72 passed`。
- Ruff 格式检查：4 个文件均已格式化。
- Ruff 静态检查：通过。
- 简体中文检查：通过。

## 风险与回滚

- 该实现保留 Decimal 的任意有限精度与数量级，不依赖可能溢出的浮点转换。
- `sNaN` 先由 `is_finite()` 拒绝，避免对该值执行比较并触发 Decimal 上下文异常。
- 如需回滚，仅回退本次提交；本次变更无外部副作用。
