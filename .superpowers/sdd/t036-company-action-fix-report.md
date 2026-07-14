# T036 公司行动审查修复报告

## 修复范围

- `require_company_actions_for_adjustment` 现在逐条校验公司行动的 `security_id`。
  缺少归属的兼容记录会被拒绝，不会作为目标证券的复权依据；任一行动属于其他证券时，
  会以中文错误阻断混杂或全异证券的记录集。
- `CompanyAction.adjustment_ratio` 仅接受有限且大于零的真实数值；显式拒绝 `bool`、
  字符串、`NaN`、无穷大、零和负数，并统一返回中文 `ValueError`。
- 未改变 `is_usable_for_current_prediction` 的布尔准入契约；未涉及视图层、网络请求、
  预测交易或外部副作用。

## TDD 证据

先向失败用例增加以下覆盖并执行：

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -v
```

新增用例在实现前得到 `5 failed, 53 passed`：`True` 被错误接受，字符串触发了非领域
`TypeError`，且未知归属、非目标证券、混杂证券行动集均未被阻断。

最小实现后，同一失败用例文件为 `58 passed`；最终与时点完整性属性测试联合复验为
`63 passed`。

## 质量验证

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py tests/property/test_point_in_time_integrity.py -v
py -3.12 -m ruff format --check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
py -3.12 -m ruff check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
py -3.12 tools/check_chinese_project_text.py src/stock_agent/domain tests/failure/test_market_data_failures.py
```

- 最终失败用例与时点完整性属性测试：`63 passed`。
- 指定范围 Ruff 格式检查和静态检查通过。
- 指定范围简体中文检查通过。
- 扩展运行 `tests/property/test_market_rules.py` 时仍有既有失败：其构造六码港股代码，
  被既有五位港股代码规则拒绝；该失败与本修复无关。

## 风险与回滚

- 兼容的无 `security_id` 公司行动不再可用于目标证券复权；调用方须补齐可验证证券归属。
- 如需回滚，仅回退本次提交即可；本次没有访问网络、生成预测或发起交易。
