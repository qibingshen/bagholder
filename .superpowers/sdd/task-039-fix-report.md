# T039 独立审查修复报告

## 修复范围

- `resolve_security_identity` 改为返回 `InstrumentCatalogEntry`，保留 `InstrumentIdentity`、`source_id`、`collected_at` 与 `data_version`，不再把目录事实降级为裸身份。
- `MarketStatus.market_time` 和 `HistoricalDailyBar.market_time` 必须使用所属市场的 IANA 时区：CN 为 `Asia/Shanghai`，HK 为 `Asia/Hong_Kong`，US 为 `America/New_York`。历史日线同时校验交易日等于该市场时间的本地日期。
- `InstrumentIdentity` 在公开构造时执行完整市场、交易所、币种和代码格式校验；新增 `InstrumentIdentityInput` 作为原始输入 DTO，仅在失败场景收集后通过 `to_identity()` 转换并统一拒绝无效输入。
- 显式传入空 `instruments` 时保持为空目录，解析返回明确的目录缺失错误，不回退内置样例。

## TDD 记录

先新增目录解析溯源、历史日线 IANA 时区、本地交易日和原始市场标识的失败测试。红灯命令与结果：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -k '目录解析入口 or IANA or 显式空证券目录' -v
```

结果为 2 项预期失败：解析入口返回 `InstrumentIdentity` 而非目录事实；历史日线接受 UTC 市场时间。

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k '证券身份拒绝市场交易所或币种不一致' -v
```

结果为 4 项预期失败：无效市场、交易所或币种组合可直接构造 `InstrumentIdentity`。

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k '非正式市场标识' -v
```

结果为 1 项预期失败：字符串 `"CN"` 可绕过 `Market` 枚举校验。

## 验证结果

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
```

结果：`85 passed`。

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k '新浪代码规范化拒绝不支持的有效市场 or 原始证券输入转换 or 证券身份拒绝市场交易所或币种不一致 or 未带市场标识的非唯一显示代码' -v
```

结果：`12 passed, 39 deselected`。

```powershell
py -3.12 -m ruff format --check src/stock_agent/application/market_service.py src/stock_agent/domain/market.py tests/contract/test_market_data_contract.py tests/failure/test_market_data_failures.py
py -3.12 -m ruff check src/stock_agent/application/market_service.py src/stock_agent/domain/market.py tests/contract/test_market_data_contract.py tests/failure/test_market_data_failures.py
py -3.12 tools/check_chinese_project_text.py src
git diff --check
```

结果：均通过。

## 关注项

完整运行 `tests/failure/test_market_data_failures.py` 的结果为 `42 passed, 9 failed`。失败项均位于当前预测可用性与公司行动/复权历史能力，涉及 `is_usable_for_current_prediction` 未拒绝不可用状态，以及 `CompanyAction`/`require_company_actions_for_adjustment` 尚未实现的接口；不属于本次 T039 市场目录、状态和日线查询修复范围。
