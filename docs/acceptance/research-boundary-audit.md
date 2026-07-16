# T128 研究边界审计

## 审计范围

本记录复核首个阶段是否存在券商连接、真实交易、收益承诺、MCP 管理工具或凭据泄露入口。审计对象包括规格、MCP 契约、权限守卫、凭据服务、预测展示、日志脱敏、备份排除和相关测试。

## 审计结论

当前结论：未发现已实现的券商连接、真实下单、自动交易、收益承诺或 MCP 管理工具入口。Finnhub 仅作为用户自带合法凭据的数据源候选；凭据仅通过系统钥匙串引用保存，不进入页面摘要、MCP 结果、日志或备份清单。

## 关键证据

| 边界 | 证据位置 | 当前结论 |
| --- | --- | --- |
| 无券商连接和真实交易 | `src/stock_agent/application/research_scope_guard.py`、`tests/contract/test_research_scope_guard.py` | 券商登录、下单、自动交易和券商凭据入口被范围守卫拒绝 |
| MCP 只读研究边界 | `src/stock_agent/mcp/permissions.py`、`src/stock_agent/adapters/mcp/management_guard.py`、`tests/contract/test_mcp_permissions.py`、`tests/failure/test_model_governance_failures.py` | 发布、回滚、删除、凭据、券商和交易工具默认拒绝 |
| 凭据不泄露 | `src/stock_agent/application/data_source_credential_service.py`、`tests/contract/test_data_source_credentials.py`、`tests/failure/test_credential_exposure.py` | 页面、状态、日志和公开记录不包含密钥或钥匙串引用 |
| 备份不包含凭据 | `src/stock_agent/application/backup_service.py`、`tests/failure/test_backup_recovery_failures.py` | `.env`、`.key` 和 credential 路径被排除 |
| 无收益承诺和买卖指令 | `src/stock_agent/domain/prediction.py`、`src/stock_agent/application/prediction_presenter.py`、`tests/contract/test_prediction_contract.py`、`tests/contract/test_prediction_presenter.py` | 预测输出和展示层拒绝收益承诺、保证性表达和买卖指令 |

## 可复跑证据

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_research_scope_guard.py tests/contract/test_mcp_permissions.py tests/failure/test_model_governance_failures.py tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py tests/failure/test_backup_recovery_failures.py tests/contract/test_prediction_contract.py tests/contract/test_prediction_presenter.py -q
```

## 保留限制

- 本审计不证明真实数据供应商授权状态，只证明当前代码不会把授权状态伪装为交易能力。
- 后续若新增导出、通知、插件、MCP 工具或桌面菜单入口，必须重新执行本审计。
- 若未来阶段要接入券商或真实交易，必须先修改宪法、规格、计划、契约、任务和权限模型；首个阶段不得通过隐藏配置绕过。
