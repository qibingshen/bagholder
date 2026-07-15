# Task 4：新浪/Finnhub 配置与选择证据

先完整阅读本文件；这是唯一任务要求来源。

## 目标

使桌面数据源管理能够显示新浪与 Finnhub 的受控配置状态，并形成可复核的数据源选择记录。新浪为公开只读 A 股候选；Finnhub 为需系统钥匙串授权的美股候选。

## 文件

- 修改 `src/stock_agent/application/data_source_credential_service.py`
- 修改 `src/stock_agent/desktop/pages/data_source_page.py`
- 创建 `docs/acceptance/data-source-selection.md`
- 修改 `tests/contract/test_data_source_credentials.py`

## 规则

- 增加不可变数据源配置元数据，至少包含 `source_id`、支持市场、是否需要凭据、访问状态和明确降级说明。
- 新浪：支持 `CN`，不需要凭据，状态只能表明“公开只读且不保证实时”；页面不得承诺实时。
- Finnhub：支持 `US`，需要凭据；使用既有 `KeyringCredentialStore` 路径，仅保存引用；未授权时页面显示受限，不能显示为可用美股实时数据。
- 页面摘要、审计输入和普通状态对象不得出现明文密钥或钥匙串引用。
- 选择记录必须说明：新浪 URL 能力与局限、市场时间/新鲜度限制、Finnhub 用户自带合法密钥、无密钥降级、数据源不混合且不绕过许可。

## 约束

- 项目文字、注释、文档字符串与测试说明使用简体中文。
- 不实现 Finnhub HTTP 调用、真实网络访问、券商、交易、下单或自动交易。
- 必须先写失败测试并确认失败，再最小实现；不得修改范围外文件。

## 测试

覆盖新浪公开只读元数据、Finnhub 未授权受限、配置后授权、页面中不出现 `test-secret` 或 `platform-keychain://`、撤销后返回受限。

运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py -v
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

## 报告

完成后可只提交本任务文件，建议 `feat: configure sina and finnhub market sources`。详细报告写入 `.superpowers/sdd/task-4-report.md`，列出文件、TDD 失败/通过证据、命令、提交、自检和 concerns；最终仅回复状态、哈希、测试摘要和 concerns。
