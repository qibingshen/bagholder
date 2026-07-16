# 桌面关键页面状态矩阵

本矩阵是页面实现前的共同验收边界。任何量化数字均须显示来源、市场时间、采集时间、数据版本与新鲜度；预测、报告和研究对话还必须显示“研究参考，不构成投资建议”。页面不得以缓存或历史快照伪装实时结果。

| 页面 | 空状态 | 加载状态 | 离线或过期状态 | 权限受限状态 | 恢复路径 |
| --- | --- | --- | --- | --- | --- |
| 市场与证券 | 提示选择市场或证券，不显示编造行情 | 显示查询范围和不含数字的加载占位 | 显示最后有效来源、时间、新鲜度与不可生成当前预测提示 | 显示数据源未授权和可读取范围 | 重新授权或导入本地历史数据后刷新 |
| 板块与自定义板块 | 提示无成员或无当时有效成员 | 显示覆盖范围加载中 | 标记数据不完整，不输出轮动排名 | 禁止修改成员并说明权限原因 | 恢复来源后以当时成员版本重新计算 |
| 预测与复盘 | 提示没有可用预测或没有到期结果 | 显示模型、数据版本加载中 | 阻断当前预测，仅可查看带版本的历史快照 | 禁止模型管理和凭据操作 | 数据恢复后重新查询，不修改预测快照 |
| 报告与任务 | 提示尚无报告或任务 | 显示任务状态和关联标识 | 显示部分成功、失败范围与安全恢复动作 | 禁止取消、重试或管理操作 | 按任务状态机重试、恢复或查看错误 |
| 模型中心 | 提示没有候选模型 | 显示门禁证据加载中 | 显示最后已验证模型，不切换正式指针 | 仅本机桌面批准角色可见发布/回滚确认 | 补齐门禁证据后重新申请批准 |
| 数据源管理 | 提示尚未配置授权数据源 | 显示凭据引用状态，不显示明文 | 显示本地导入历史数据的限制 | 显示系统安全存储不可用或权限拒绝 | 重新授权、重新打开安全存储或切换至本地历史数据 |

所有页面的恢复操作必须保留原始行情、预测快照和已验证报告；不得通过覆盖或删除历史事实来恢复。

## T121 核对结论

本次核对覆盖市场与证券、板块与自定义板块、预测与复盘、报告与任务、模型中心、数据源管理以及研究对话相关页面。当前结论是：关键页面均已有可绑定的本地状态模型或页面视图模型；非 READY 状态不得补造行情、预测、板块排名、报告或对话数字；预测、报告、模型中心和研究对话均必须展示“研究参考，不构成投资建议”。

## 差异记录

| 页面 | 当前实现状态 | 与矩阵差异 | 处理结论 |
| --- | --- | --- | --- |
| 市场与证券 | `MarketPageState`、`SecurityPageState` 覆盖 EMPTY、LOADING、OFFLINE、PERMISSION_DENIED、STALE、CLOSED、READY、RECOVERED | 与矩阵一致，RECOVERED 会按 STALE 基础状态恢复并重新验证 | 已满足 |
| 板块与自定义板块 | `SectorPageState` 使用 EMPTY、LOADING、READY、INCOMPLETE、NO_MEMBERS 表达空、加载、可用、数据不完整和无成员 | 未使用通用 OFFLINE/PERMISSION_DENIED 命名；当前用 INCOMPLETE/NO_MEMBERS 阻止排名和轮动输出 | 记录为命名差异，业务门禁已满足 |
| 预测与复盘 | `PredictionPageState`、`HistoryReviewView` 覆盖空、加载、离线、权限受限、过期、历史快照、待验证和可用状态 | 与矩阵一致，历史预测快照保持只读 | 已满足 |
| 报告与任务 | `ReportPageState`、`TaskCenterPageState` 使用 LOADING、OFFLINE、PARTIAL_SUCCESS、RECOVERED/RECOVERABLE、READY | 未单独命名 EMPTY/PERMISSION_DENIED；当前阶段以无报告/无任务列表和任务权限门禁表达 | 记录为阶段差异，T123 全量测试前继续保留观察 |
| 模型中心 | `ModelManagementPageState` 覆盖 READY_TO_RELEASE、BLOCKED、ROLLBACK_CONFIRM_REQUIRED | 未使用通用 EMPTY/LOADING/OFFLINE 命名；当前聚焦门禁证据、发布确认和回滚确认 | 已满足 US7 门禁，通用空/加载视图留到 PySide6 组件阶段 |
| 数据源管理 | `DataSourcePageState` 从脱敏授权选择记录生成页面摘要，`DataManagementPageState` 覆盖备份、恢复、容量和删除确认 | 数据源页未单独建 LOADING/OFFLINE 状态；授权受限和降级说明已由选择记录承载 | 已满足当前凭据安全边界 |
| 研究对话 | `ResearchChatPageState`、`ResearchChatAnswerView` 覆盖 EMPTY、LOADING、READY、PERMISSION_DENIED、OFFLINE | 矩阵原表未单列研究对话，但它属于 AI 解释与 MCP 溯源关键页面 | 已补充纳入核对范围 |

## 修复证据

本次核对后新增文档检查 `tests/contract/test_desktop_state_matrix_doc.py`，确保矩阵持续包含关键页面、差异记录、修复证据和固定风险提示。建议复跑以下命令：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_desktop_state_contract.py tests/contract/test_prediction_page_contract.py tests/contract/test_sector_page_contract.py tests/contract/test_report_task_pages.py tests/contract/test_model_management_page.py tests/contract/test_data_management_page.py tests/contract/test_data_source_credentials.py tests/contract/test_research_chat_page_contract.py tests/contract/test_desktop_state_matrix_doc.py -q
```

若后续将板块、报告/任务、模型中心或数据源管理页面统一改为通用 EMPTY、LOADING、OFFLINE、PERMISSION_DENIED 状态名，必须同步更新本矩阵和对应页面契约测试。当前阶段不得为了填满状态名而伪造不具备业务含义的页面状态。
