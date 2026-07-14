# Task 4：新浪与 Finnhub 配置及选择证据报告

## 完成文件

- `src/stock_agent/application/data_source_credential_service.py`
- `src/stock_agent/desktop/pages/data_source_page.py`
- `tests/contract/test_data_source_credentials.py`
- `docs/acceptance/data-source-selection.md`

## 实现摘要

- 增加不可变数据源元数据：新浪仅支持 `CN`、公开只读且不保证实时；Finnhub 仅支持 `US`、需要凭据且未授权时受限。
- 增加不含明文密钥和钥匙串引用的选择记录，包含市场、凭据需求、访问状态、降级说明和审计说明。
- Finnhub 配置后显示“已授权”，撤销后恢复“受限”；新浪拒绝凭据配置。
- 页面新增从脱敏选择记录生成摘要的入口，不展示明文密钥或钥匙串引用。
- 补充验收文档，明确 URL 能力、市场时间与新鲜度限制、合法密钥、无密钥降级、不混用和不绕过许可。

## TDD 证据

先在 `tests/contract/test_data_source_credentials.py` 添加新浪元数据与 Finnhub 授权生命周期测试，再运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py -v
```

失败结果：新增两个测试均因 `DataSourceCredentialService` 缺少 `selection_record` 报 `AttributeError`；原有四个测试通过。随后完成最小实现。

## 验证命令与结果

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py -v
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

结果：8 个测试全部通过；Ruff 格式检查通过（55 个文件已格式化）；Ruff 静态检查通过。

## 自检

- 选择记录和页面摘要均不从 `CredentialAuthorization.credential_reference` 取值。
- 本任务未新增 Finnhub HTTP、网络、券商、交易、下单或自动交易实现。
- 仅修改任务要求的 4 个业务、测试和文档文件，并新增本报告。

## Concerns

- 当前桌面层仅提供页面状态模型；实际 PySide6 视图尚未在本任务范围内，因此调用方需要使用 `from_selection_record` 渲染选择摘要。
