# 任务：本地量化股票分析智能体

**输入**：`specs/001-local-stock-agent/` 下的 `spec.md`、`plan.md`、`research.md`、`data-model.md`、
`quickstart.md`、`contracts/` 和质量清单。
**前置产物**：实施计划、规格、澄清记录、研究、数据模型与契约均已完成。

**测试纪律**：项目采用测试驱动开发。每个用户故事的契约测试、数据时点测试和失败场景测试均先于
对应实现任务，并必须先因缺少实现而失败。宪法约束测试不可省略。

## 格式

- `[P]` 表示可与同阶段其他不同文件任务并行。
- `[USn]` 映射规格的用户故事；基础设施与最终阶段不带故事标签。
- 每项任务都包含准确文件路径；不可将测试、实现或审计责任留给口头约定。

## 阶段 1：项目准备

**目的**：建立跨平台、本地优先和测试驱动的工程骨架。

- [x] T001 创建 Python 包、测试、打包和本地运行目录结构：`pyproject.toml`、`src/stock_agent/`、`tests/`、`packaging/`
- [x] T002 配置 Python 3.12、PySide6、DuckDB、PyArrow、Pydantic、MCP SDK、pytest 与 Hypothesis 依赖：`pyproject.toml`
- [x] T003 [P] 配置 Ruff、Black、mypy、pytest 和覆盖率命令：`pyproject.toml`、`ruff.toml`、`mypy.ini`
- [x] T004 [P] 配置凭据、运行时目录、暂存工件和测试数据排除规则：`.gitignore`、`.env.example`
- [x] T005 [P] 建立 Windows、macOS、Linux 平台路径与安全存储接口骨架：`src/stock_agent/adapters/platform/`
- [x] T006 [P] 建立结构化脱敏日志和关联标识基础设施：`src/stock_agent/application/observability.py`
- [x] T007 [P] 建立共享测试夹具、冻结市场时间和临时本地数据根目录：`tests/conftest.py`
- [x] T008 [P] 配置简体中文文档、注释、文档字符串和示例检查规则：`tools/check_chinese_project_text.py`、`tests/unit/test_chinese_conventions.py`
- [x] T009 创建本地服务、桌面、工作者、训练和 MCP 启动入口占位：`src/stock_agent/bootstrap/`
- [x] T010 记录开发、测试和三平台本地运行命令：`README.md`

## 阶段 2：宪法基础门禁（阻塞）

**目的**：建立所有用户故事共同依赖的版本、权限、存储、市场规则、任务与审计边界。

**关键门禁：本阶段未完成前不得开始任何用户故事实现。**

- [x] T011 定义通用结果、错误、溯源、新鲜度、分页、超时、资源限额与幂等键运行时 schema，并先建立关键页面状态矩阵：`src/stock_agent/contracts/common.py`、`docs/acceptance/desktop-state-matrix.md`
- [x] T012 [P] 定义市场、证券、交易日历、版本、任务、模型和审计领域值对象：`src/stock_agent/domain/`
- [x] T013 [P] 编写通用契约字段、错误脱敏和缺失元数据的失败测试并确认先失败：`tests/contract/test_common_contract.py`
- [x] T014 [P] 编写证券代码歧义、市场时区、交易日历和币种比较的数据属性测试并确认先失败：`tests/property/test_market_rules.py`
- [x] T015 [P] 编写凭据配置参数校验、安全存储引用、重新授权、凭据不进入日志/普通导出/备份/MCP 结果的失败测试并确认先失败：`tests/failure/test_credential_exposure.py`、`tests/contract/test_data_source_credentials.py`
- [x] T016 实现 DuckDB 元数据连接、迁移和事务边界：`src/stock_agent/adapters/storage/duckdb_store.py`、`src/stock_agent/bootstrap/migrations/`
- [x] T017 实现 Parquet 版本目录、清单、哈希和完成标记：`src/stock_agent/adapters/storage/parquet_store.py`
- [x] T018 实现 SQLite 桌面状态存储且禁止量化事实写入：`src/stock_agent/adapters/storage/sqlite_settings.py`
- [x] T019 实现“暂存—校验—原子提交”版本服务和父版本引用：`src/stock_agent/application/versioning_service.py`
- [x] T020 编写追加保存、静默覆盖拒绝、版本链重建和暂存失败不污染数据测试：`tests/integration/test_versioning_atomic_commit.py`
- [x] T021 实现版本化市场规则、交易日历、公司行动和汇率不可比较降级服务：`src/stock_agent/domain/market_rules.py`
- [x] T022 编写预测时点可用性、未来数据泄漏、复权、成员历史和汇率时点测试并确认先失败：`tests/property/test_point_in_time_integrity.py`
- [x] T023 实现平台数据根目录、运行时锁、凭据库引用、数据源凭据配置/撤销用例及桌面受限状态入口：`src/stock_agent/adapters/platform/paths.py`、`src/stock_agent/adapters/platform/credential_store.py`、`src/stock_agent/application/data_source_credential_service.py`、`src/stock_agent/desktop/pages/data_source_page.py`
- [x] T024 实现持久化任务实体、去重键和状态机：`src/stock_agent/application/task_service.py`、`src/stock_agent/domain/task.py`
- [x] T025 编写任务状态迁移、取消、重试、中断恢复和重复提交测试并确认先失败：`tests/unit/test_task_state_machine.py`
- [x] T026 实现本地应用服务的权限、参数校验、审计和事务协调入口：`src/stock_agent/application/local_service.py`
- [x] T027 编写后台进程崩溃、取消、磁盘不足和桌面可用性失败测试并确认先失败：`tests/failure/test_worker_failure_isolation.py`
- [x] T028 实现工作进程暂存提交协议和结构化任务事件：`src/stock_agent/workers/runner.py`、`src/stock_agent/contracts/worker_events.py`
- [x] T029 实现禁止券商、真实交易和交易凭据依赖的范围守卫：`src/stock_agent/application/research_scope_guard.py`
- [x] T030 编写券商、下单、自动交易和越权工具注册拒绝测试：`tests/contract/test_research_scope_guard.py`
- [x] T031 实现日志关联、凭据脱敏和审计事件追加服务：`src/stock_agent/application/audit_service.py`
- [x] T032 编写日志脱敏、审计追加和数字溯源基础测试：`tests/unit/test_observability_and_audit.py`
- [x] T033 运行基础存储、时间一致性、任务隔离和范围守卫测试并记录门禁结果：`tests/contract/`、`tests/property/`、`tests/failure/`、`docs/acceptance/foundation-gate-results.md`

## 阶段 3：用户故事 1——查看跨市场行情与个股信息（P1）

**目标**：交付一个市场的历史日线采集、版本化保存、市场状态和个股历史展示闭环，并为三市场扩展保留适配器边界。

**独立验收**：在不使用预测、板块或对话功能时，用户能选择市场与证券，查看主要指数、历史行情、
来源、市场时间、采集时间、数据版本和新鲜度。

### 用户故事 1 测试（实现前必做）

- [x] T034 [P] [US1] 编写市场状态、历史行情、新鲜度以及市场/证券页面空、加载、离线、权限受限和恢复状态契约测试并确认先失败：`tests/contract/test_market_data_contract.py`、`tests/contract/test_desktop_state_contract.py`
- [x] T035 [P] [US1] 编写 A 股 5 秒、港股/美股 15 秒、60 秒、15 分钟与休市边界数据测试并确认先失败：`tests/property/test_freshness_rules.py`
- [x] T036 [P] [US1] 编写数据源缺字段、过期、代码歧义和公司行动失败场景测试并确认先失败：`tests/failure/test_market_data_failures.py`
- [x] T037 [P] [US1] 按 `research.md` R-008 形成首个授权数据源的可复核选择记录，并编写一市场历史日线适配器、标准化和原子保存集成测试并确认先失败：`docs/acceptance/data-source-selection.md`、`tests/integration/test_single_market_daily_pipeline.py`

### 用户故事 1 实现

- [x] T038 [P] [US1] 实现可插拔市场数据适配器协议和授权状态接口：`src/stock_agent/adapters/market_data/base.py`
- [x] T039 [US1] 实现证券目录、市场状态和交易日历查询用例：`src/stock_agent/application/market_service.py`
- [x] T040 [US1] 实现一市场历史日线采集、原始响应保存和标准化工作者：`src/stock_agent/workers/market_ingestion.py`
- [x] T041 [US1] 实现行情新鲜度、休市和过期预测阻断规则：`src/stock_agent/domain/freshness.py`
- [x] T042 [US1] 实现 K 线、成交量、指标和来源元数据查询视图模型：`src/stock_agent/desktop/viewmodels/security_view_model.py`
- [x] T043 [US1] 按已建立的状态矩阵实现市场总览和个股研究页面的空、加载、离线、权限受限、过期与恢复状态：`src/stock_agent/desktop/pages/market_page.py`、`src/stock_agent/desktop/pages/security_page.py`、`docs/acceptance/desktop-state-matrix.md`
- [x] T044 [US1] 接入主要指数与历史日线本地展示闭环：`src/stock_agent/desktop/controllers/market_controller.py`
- [ ] T045 [US1] 补充一市场行情闭环独立验收证据、中文使用说明和至少 90% 目标用户在 3 分钟内完成核心旅程的可用性验收记录：`docs/acceptance/us1-market-history.md`、`docs/acceptance/us1-usability-study.md`
- [x] T046 [US1] 运行 US1 契约、数据、失败和集成测试并记录结果：`tests/contract/test_market_data_contract.py`、`tests/property/test_freshness_rules.py`、`tests/failure/test_market_data_failures.py`、`tests/integration/test_single_market_daily_pipeline.py`

## 阶段 4：用户故事 2——获得可解释的概率预测（P1）

**目标**：交付 1/5/20 交易日三分类概率预测、版本化快照、解释、风险披露和过期数据阻断。

**独立验收**：选择有有效数据的证券，单独查看完整预测字段；使用过期数据时不能生成当前预测。

### 用户故事 2 测试（实现前必做）

- [x] T047 [P] [US2] 编写预测输入输出、概率和免责声明契约测试并确认先失败：`tests/contract/test_prediction_contract.py`
- [x] T048 [P] [US2] 编写 1/5/20 交易日、±1%/±3%/±6% 标签与概率容差数据测试并确认先失败：`tests/property/test_prediction_labels.py`
- [x] T049 [P] [US2] 编写过期/缺失数据、无有效到期价格和版本回写拒绝测试并确认先失败：`tests/failure/test_prediction_failures.py`

### 用户故事 2 实现

- [x] T050 [P] [US2] 实现特征快照、标签规则和简单基准领域模型：`src/stock_agent/domain/feature_snapshot.py`、`src/stock_agent/domain/prediction.py`
- [x] T051 [US2] 实现按预测时点生成特征、简单基准概率和预测快照用例：`src/stock_agent/application/prediction_service.py`
- [x] T052 [US2] 实现预测快照追加保存、模型/特征/数据版本关联和到期结果回填：`src/stock_agent/adapters/storage/prediction_repository.py`
- [x] T053 [US2] 实现预测解释、风险因素、新鲜度和免责声明输出组装：`src/stock_agent/application/prediction_presenter.py`
- [x] T054 [US2] 实现预测详情页面、历史快照和过期/待验证状态：`src/stock_agent/desktop/pages/prediction_page.py`
- [x] T055 [US2] 实现当前预测阻断与历史预测降级展示：`src/stock_agent/desktop/controllers/prediction_controller.py`
- [x] T056 [US2] 编写预测独立验收说明与固定风险提示检查：`docs/acceptance/us2-prediction-safety.md`
- [x] T057 [US2] 运行 US2 契约、数据和失败场景测试并记录结果：`tests/contract/test_prediction_contract.py`、`tests/property/test_prediction_labels.py`、`tests/failure/test_prediction_failures.py`

## 阶段 5：用户故事 3——用自然语言完成研究查询（P1）

**目标**：交付本机默认只读 MCP 查询、非破坏性分析启动、Skill 编排和量化数字溯源。

**独立验收**：使用固定问句查询行情、预测、报告和无法回答场景；每个数字可回到工具结果，失败时不编造数字。

### 用户故事 3 测试（实现前必做）

- [x] T058 [P] [US3] 编写 MCP 通用信封、严格工具参数、分页游标、版本演进、错误与溯源契约测试并确认先失败：`tests/contract/test_mcp_contract.py`
- [x] T059 [P] [US3] 编写非本机、发布、回滚、删除、凭据和券商工具拒绝测试并确认先失败：`tests/contract/test_mcp_permissions.py`
- [x] T060 [P] [US3] 编写工具超时、资源限额、幂等键、部分结果、过期数字、Skill 越权调用和大模型拒绝补造数字测试并确认先失败：`tests/failure/test_skill_numeric_provenance.py`

### 用户故事 3 实现

- [x] T061 [P] [US3] 实现 MCP stdio 启动、受控本机传输和工具注册表：`src/stock_agent/adapters/mcp/server.py`
- [x] T062 [US3] 实现市场、预测、回测、报告、任务和模型只读 MCP 工具：`src/stock_agent/adapters/mcp/tools/`
- [x] T063 [US3] 实现非破坏性分析任务启动、超时和结构化错误映射：`src/stock_agent/adapters/mcp/task_tools.py`
- [x] T064 [US3] 实现每日分析、个股诊断、板块轮动、预测复盘和模型评估 Skill 清单：`src/stock_agent/skills/`
- [x] T065 [US3] 实现工具结果引用、数字溯源和拒绝回答的对话编排器：`src/stock_agent/application/research_chat_service.py`
- [x] T066 [US3] 实现研究对话页面及工具失败、无数据和权限拒绝状态：`src/stock_agent/desktop/pages/research_chat_page.py`
- [x] T067 [US3] 运行 US3 MCP、最小权限、数字溯源和失败场景测试并记录结果：`tests/contract/test_mcp_contract.py`、`tests/contract/test_mcp_permissions.py`、`tests/failure/test_skill_numeric_provenance.py`

## 阶段 6：用户故事 4——分析主要板块与自定义板块（P2）

**目标**：交付主要板块指标、历史成员关系、自定义板块和轮动研究。

**独立验收**：创建并修改自定义板块后，分别在变更前后历史时点分析，确认只使用当时有效成员。

### 用户故事 4 测试（实现前必做）

- [x] T068 [P] [US4] 编写板块、成员有效期、指标和覆盖率契约测试并确认先失败：`tests/contract/test_sector_contract.py`
- [x] T069 [P] [US4] 编写成员增删历史、点时成员查询和跨市场成员数据测试并确认先失败：`tests/property/test_sector_membership_history.py`
- [x] T070 [P] [US4] 编写成员历史断裂、覆盖率不足和禁止误导性排名失败测试并确认先失败：`tests/failure/test_sector_failures.py`

### 用户故事 4 实现

- [x] T071 [P] [US4] 实现板块、成员关系和有效区间仓储：`src/stock_agent/adapters/storage/sector_repository.py`
- [x] T072 [US4] 实现主要板块指标、覆盖率、趋势强度和轮动用例：`src/stock_agent/application/sector_service.py`
- [x] T073 [US4] 实现自定义板块创建、归档和追加式成员变更用例：`src/stock_agent/application/custom_sector_service.py`
- [x] T074 [US4] 实现点时成员查询与历史分析阻断规则：`src/stock_agent/domain/sector_membership.py`
- [x] T075 [US4] 实现板块总览、自定义板块和成员历史页面：`src/stock_agent/desktop/pages/sector_page.py`、`src/stock_agent/desktop/pages/custom_sector_page.py`
- [x] T076 [US4] 实现板块轮动、数据不完整和无成员空状态展示：`src/stock_agent/desktop/controllers/sector_controller.py`
- [x] T077 [US4] 编写板块独立验收说明：`docs/acceptance/us4-sector-history.md`
- [x] T078 [US4] 运行 US4 契约、成员历史和失败场景测试并记录结果：`tests/contract/test_sector_contract.py`、`tests/property/test_sector_membership_history.py`、`tests/failure/test_sector_failures.py`

## 阶段 7：用户故事 5——自动更新并阅读每日研究报告（P2）

**目标**：交付按市场日历调度的数据更新、每日报告、失败降级、任务恢复和通知。

**独立验收**：模拟正常、部分数据源失败和任务中断，验证报告版本、降级、重试和既有数据安全。

### 用户故事 5 测试（实现前必做）

- [ ] T079 [P] [US5] 编写每日调度、报告和任务状态契约测试并确认先失败：`tests/contract/test_daily_report_contract.py`
- [ ] T080 [P] [US5] 编写 A/HK/US 默认时点、休市、半日市和夏令时调度数据测试并确认先失败：`tests/property/test_market_scheduler.py`
- [ ] T081 [P] [US5] 编写源失败、限频、取消、中断和部分报告失败场景测试并确认先失败：`tests/failure/test_daily_task_recovery.py`

### 用户故事 5 实现

- [ ] T082 [P] [US5] 实现按版本化市场日历和市场时区计算的每日调度器：`src/stock_agent/application/daily_scheduler.py`
- [ ] T083 [US5] 实现行情更新、预测复盘、报告生成和通知工作者：`src/stock_agent/workers/daily_pipeline.py`
- [ ] T084 [US5] 实现日报快照、缺失范围、降级影响和版本化存储：`src/stock_agent/application/report_service.py`
- [ ] T085 [US5] 实现任务列表、重试、取消、恢复和通知视图模型：`src/stock_agent/desktop/viewmodels/task_view_model.py`
- [ ] T086 [US5] 实现报告中心和任务中心的加载、离线、部分成功和恢复状态：`src/stock_agent/desktop/pages/report_page.py`、`src/stock_agent/desktop/pages/task_page.py`
- [ ] T087 [US5] 编写每日任务与报告独立验收说明：`docs/acceptance/us5-daily-reports.md`
- [ ] T088 [US5] 运行 US5 调度、契约、恢复和失败场景测试并记录结果：`tests/contract/test_daily_report_contract.py`、`tests/property/test_market_scheduler.py`、`tests/failure/test_daily_task_recovery.py`

## 阶段 8：用户故事 6——复盘历史预测与简单基准（P2）

**目标**：交付历史预测、到期结果、简单基准、时间序列回测和不可成交约束的复盘能力。

**独立验收**：已到期预测显示原快照、实际结果和基准比较；未到期预测不提前判定，原快照不被修订覆盖。

### 用户故事 6 测试（实现前必做）

- [ ] T089 [P] [US6] 编写回测窗口、成本、版本和结果契约测试并确认先失败：`tests/contract/test_backtest_contract.py`
- [ ] T090 [P] [US6] 编写扩展/滚动窗口、标签隔离和无未来数据泄漏测试并确认先失败：`tests/property/test_time_series_backtest.py`
- [ ] T091 [P] [US6] 编写手续费、滑点、停牌、涨跌停、流动性和不可成交失败场景测试并确认先失败：`tests/failure/test_backtest_trading_constraints.py`

### 用户故事 6 实现

- [ ] T092 [P] [US6] 实现滚动和扩展窗口切分器及标签观察期隔离：`src/stock_agent/application/time_series_splitter.py`
- [ ] T093 [US6] 实现版本化简单基准、概率指标和分市场/周期比较服务：`src/stock_agent/application/backtest_service.py`
- [ ] T094 [US6] 实现交易摩擦、停牌和不可成交模拟规则：`src/stock_agent/domain/trading_constraints.py`
- [ ] T095 [US6] 实现预测到期实际结果、历史快照和回测结果仓储：`src/stock_agent/adapters/storage/backtest_repository.py`
- [ ] T096 [US6] 实现历史预测复盘、基准比较和待验证状态页面：`src/stock_agent/desktop/pages/history_review_page.py`
- [ ] T097 [US6] 运行 US6 契约、时间序列和不可成交失败场景测试并记录结果：`tests/contract/test_backtest_contract.py`、`tests/property/test_time_series_backtest.py`、`tests/failure/test_backtest_trading_constraints.py`

## 阶段 9：用户故事 8——跨平台保存与恢复研究状态（P2）

**目标**：交付一致性备份、隔离恢复、容量门禁和三平台数据/设置/任务恢复。

**独立验收**：在各目标平台创建备份并于干净环境恢复；损坏备份不覆盖现有数据。

### 用户故事 8 测试（实现前必做）

- [ ] T098 [P] [US8] 编写备份清单、哈希、版本链和跨平台恢复契约测试并确认先失败：`tests/contract/test_backup_contract.py`
- [ ] T099 [P] [US8] 编写 200 GB、80% 门禁、分钟线选择上限和路径适配数据测试并确认先失败：`tests/property/test_storage_budget.py`
- [ ] T100 [P] [US8] 编写损坏包、中断恢复、凭据排除和不可变工件删除拒绝测试并确认先失败：`tests/failure/test_backup_recovery_failures.py`

### 用户故事 8 实现

- [ ] T101 [P] [US8] 实现备份清单、一致性快照和哈希验证服务：`src/stock_agent/application/backup_service.py`
- [ ] T102 [US8] 实现隔离恢复、只读校验和用户确认后的原子切换：`src/stock_agent/application/restore_service.py`
- [ ] T103 [US8] 实现容量预算、80% 预警和分钟线选择限制服务：`src/stock_agent/application/storage_budget_service.py`
- [ ] T104 [US8] 实现备份恢复、容量、导入导出和删除影响确认页面：`src/stock_agent/desktop/pages/data_management_page.py`
- [ ] T105 [US8] 编写三平台恢复独立验收说明：`docs/acceptance/us8-backup-restore.md`
- [ ] T106 [US8] 运行 US8 备份、容量和失败恢复测试并记录结果：`tests/contract/test_backup_contract.py`、`tests/property/test_storage_budget.py`、`tests/failure/test_backup_recovery_failures.py`

## 阶段 10：用户故事 7——监督候选模型晋级（P3）

**目标**：交付候选训练、基准比较、影子运行、本机批准、原子发布和回滚。

**独立验收**：完整候选模型可在本机批准后发布并可回滚；任一门禁缺失时不能发布。

### 用户故事 7 测试（实现前必做）

- [ ] T107 [P] [US7] 编写模型状态、评估证据、批准和回滚契约测试并确认先失败：`tests/contract/test_model_contract.py`
- [ ] T108 [P] [US7] 编写 Brier score 5%、平衡准确率 2 个百分点、分市场/周期退化和 30 交易日影子数据测试并确认先失败：`tests/property/test_model_release_gates.py`
- [ ] T109 [P] [US7] 编写严重故障、未来泄漏、未经授权发布、原子切换失败和回滚失败场景测试并确认先失败：`tests/failure/test_model_governance_failures.py`

### 用户故事 7 实现

- [ ] T110 [P] [US7] 实现候选模型注册、工件哈希和评估证据仓储：`src/stock_agent/adapters/storage/model_registry.py`
- [ ] T111 [US7] 实现独立训练进程、候选登记和无发布权限边界：`src/stock_agent/training/runner.py`
- [ ] T112 [US7] 实现时间序列评估、简单基准门禁和分组指标判定：`src/stock_agent/training/evaluation_pipeline.py`
- [ ] T113 [US7] 实现候选与正式模型并行影子运行和 30 交易日证据累积：`src/stock_agent/training/shadow_runner.py`
- [ ] T114 [US7] 实现本机桌面批准、原子发布指针和回滚审计用例：`src/stock_agent/application/model_release_service.py`
- [ ] T115 [US7] 实现模型中心、门禁证据、批准、发布和回滚确认页面：`src/stock_agent/desktop/pages/model_management_page.py`
- [ ] T116 [US7] 实现 MCP 管理动作永久拒绝与服务端二次权限检查：`src/stock_agent/adapters/mcp/management_guard.py`
- [ ] T117 [US7] 编写候选模型独立验收说明：`docs/acceptance/us7-model-governance.md`
- [ ] T118 [US7] 运行 US7 契约、发布门禁、失败与回滚测试并记录结果：`tests/contract/test_model_contract.py`、`tests/property/test_model_release_gates.py`、`tests/failure/test_model_governance_failures.py`

## 阶段 11：跨领域验证与发布证据

- [ ] T119 [P] 完成 A 股、港股、美股适配器并实现授权、冲突、限频和降级策略：`src/stock_agent/adapters/market_data/`
- [ ] T120 [P] 编写三市场适配器、来源冲突、授权失效和限频契约测试：`tests/contract/test_multi_market_adapters.py`
- [ ] T121 验证各关键页面均已实现并满足阶段 2 建立的空、加载、离线、权限受限和恢复状态矩阵，记录差异与修复证据：`docs/acceptance/desktop-state-matrix.md`
- [ ] T122 [P] 运行全量中文文档、注释、文档字符串和示例规范检查：`tools/check_chinese_project_text.py`、`tests/unit/test_chinese_conventions.py`
- [ ] T123 运行全量契约、属性、集成和失败测试并保存版本化结果：`tests/`、`docs/acceptance/test-evidence.md`
- [ ] T124 [P] 构建并验收 Windows 安装、启动、升级、核心流程与数据恢复：`packaging/windows/`、`docs/acceptance/windows-e2e.md`
- [ ] T125 [P] 构建并验收 macOS Apple Silicon/Intel 安装、启动、升级、核心流程与数据恢复：`packaging/macos/`、`docs/acceptance/macos-e2e.md`
- [ ] T126 [P] 构建并验收 Ubuntu 22.04/24.04 安装、启动、升级、核心流程与数据恢复：`packaging/linux/`、`docs/acceptance/linux-e2e.md`
- [ ] T127 核对所有预测、报告、回测模拟和相关对话产物均显示固定风险提示：`docs/acceptance/disclaimer-audit.md`
- [ ] T128 复核无券商连接、真实交易、收益承诺、MCP 管理工具或凭据泄露入口：`docs/acceptance/research-boundary-audit.md`
- [ ] T129 汇总发布证据、模型回滚演练和三平台门禁结论：`docs/acceptance/release-readiness.md`

## 依赖与执行顺序

- 阶段 1 完成后才能进入阶段 2；阶段 2 是所有用户故事的阻塞前置条件。
- P1 顺序：US1（历史行情闭环）→ US2（概率预测）→ US3（MCP 与自然语言）。
- P2 顺序：US4（板块）与 US5（每日报告）可在 US1 后并行规划；US6 依赖 US2；US8 可在阶段 2 后独立实施。
- US7 依赖 US2、US5、US6 与 US8 提供的预测、任务、评估和回滚基础。
- 阶段 11 依赖所有目标用户故事；三平台验收和回滚证据完成前不得声明全平台发布。
- 每个故事内：测试任务必须先失败，再实现；实现完成后仅在对应独立验收和测试记录完成时才可进入下一故事。

## 并行机会

- 阶段 1 的 T003–T008 可并行。
- 阶段 2 的 T013–T015、T020、T022、T025、T027、T030、T032 可在其依赖满足后并行。
- 每个用户故事的契约、数据属性和失败场景测试可并行；标有 `[P]` 的领域模型或平台工件可并行。
- US4、US5 和 US8 在阶段 2 与 US1 的市场基础完成后可由不同开发者并行实施。
- T119、T120、T122、T124、T125、T126 可在各自依赖满足后并行。

## MVP 范围与增量交付

### 第一个 MVP：US1

完成阶段 1、阶段 2 和 US1：一个授权市场的历史日线采集、标准化、版本化本地保存、市场状态、
主要指数、个股历史展示与新鲜度元数据。该闭环不依赖预测、板块、MCP 或模型发布；T119 与
T120 是正式版本在 A 股、港股、美股三市场分别完成相同验收的不可跳过发布前门禁。

### 后续增量

1. US2 增加概率预测、快照与风险披露。
2. US3 增加本机 MCP 和可追溯自然语言研究。
3. US4、US5、US6、US8 增加板块、每日报告、历史验证与跨平台恢复。
4. US7 最后增加受控候选模型晋级与回滚。

## 任务生成检查

- [ ] 每个用户故事均有独立目标、独立验收、测试先行任务和实现任务。
- [ ] 所有任务使用连续 T001–T129 编号、复选框、必要并行标记、故事标签和准确路径。
- [ ] 所有宪法强制项均映射到契约、数据、失败、平台或发布证据任务。
- [ ] 未包含券商交易、自动交易或收益承诺实现任务。
- [ ] 所有任务说明、验收证据和新增项目文档使用简体中文。
