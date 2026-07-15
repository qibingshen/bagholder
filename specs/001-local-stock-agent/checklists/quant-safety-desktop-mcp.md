# 需求质量清单：量化数据、预测安全、桌面体验与 MCP 契约

**目的**：用于正式评审本地量化股票分析智能体的规格与技术计划是否完整、清晰、一致、可衡量和可追溯；
不用于检查代码或实现行为。
**创建日期**：2026-07-10
**功能**：[本地量化股票分析智能体规格](../spec.md)
**评审对象**：[规格](../spec.md)、[计划](../plan.md)、[技术研究](../research.md)、[数据模型](../data-model.md)

## 跨市场事实、时间与币种

- [x] CHK001 是否为 A 股、港股、美股分别定义不可歧义的证券身份、显示代码与供应商代码关系，且明确代码变更和退市的历史有效期？[Completeness, Spec §FR-002/FR-004, Plan §数据版本与恢复策略]
- [x] CHK002 是否明确市场当地时间、UTC、交易日、盘前/盘中/盘后、午间或临时停市在所有行情、预测、报告和任务中的使用边界？[Completeness, Spec §FR-004, Research §R-003]
- [x] CHK003 是否量化并一致定义了 A 股 5 秒、港股/美股 15 秒、60 秒、15 分钟及休市状态的新鲜度分级？[Clarity, Spec §FR-044/SC-003]
- [x] CHK004 跨市场比较是否明确基准、原始币种、汇率来源、汇率版本和汇率时点；汇率缺失或晚于分析时点时是否规定不可比较？[Gap, Research §R-003]
- [x] CHK005 复权、公司行动、停复牌、涨跌停、代码变更和退市是否均有来源、版本、生效时间和历史分析处理要求？[Completeness, Spec §异常与边界场景, Data Model §核心实体]
- [x] CHK006 交易日历供应商、临时停市修订、半日市及夏令时变更的权威来源和版本更新频率是否明确？[Assumption, Research §R-003]

## 板块与历史成员关系

- [x] CHK007 主要板块的分类来源、层级、成员覆盖率和成员关系有效时间是否被完整定义？[Completeness, Spec §FR-007/FR-008]
- [x] CHK008 自定义板块的创建、重命名、归档、成员增删、变更来源和审计要求是否清楚且不与追加保存原则冲突？[Consistency, Spec §FR-009/FR-010, Contracts §板块与自定义板块]
- [x] CHK009 历史板块分析是否明确只能采用当时有效成员，并定义成员历史断裂时停止计算、标记覆盖率和拒绝排名的规则？[Completeness, Spec §FR-011, Spec §异常与边界场景]
- [x] CHK010 板块轮动、趋势强度、成交活跃度和上涨下跌家数的口径、观察窗口、缺失值和跨市场可比性是否量化？[Gap, Spec §FR-008]

## 行情来源、授权、新鲜度与降级

- [x] CHK011 混合授权模式是否明确用户凭据、公开数据和本地导入历史数据各自可提供的市场、粒度、时效和功能范围？[Completeness, Spec §FR-042/FR-043]
- [x] CHK012 数据源供应商评估是否有授权、覆盖、延迟、稳定性、限频、成本、历史深度、公司行动质量和退出难度的可比较准则？[Completeness, Research §R-008]
- [x] CHK013 多数据源同一时点冲突时，优先级、差异保留、人工复核触发条件及禁止静默拼接是否明确？[Clarity, Spec §异常与边界场景]
- [x] CHK014 限频、超时、授权失效、字段缺失、数据版本冲突和部分市场失败的重试资格、退避边界与用户可见降级是否分别定义？[Completeness, Plan §跨市场、错误降级与平台交付, Contracts §任务契约]
- [x] CHK015 “当前预测”对实时、准实时、延迟、过期和休市行情的可用性是否无歧义，且不会把历史快照伪装为当前预测？[Consistency, Spec §FR-015/FR-044, Contracts §预测契约]
- [x] CHK016 数据源凭据是否明确排除于报告、普通导出、备份、日志、任务参数和 MCP 结果之外，并定义恢复后的重新授权要求？[Completeness, Spec §FR-042, Research §R-006]

## 预测、标签与未来数据泄漏

- [x] CHK017 1、5、20 个“交易日”是否明确以证券所属市场有效交易日计数，而非自然日或用户本机时区？[Clarity, Spec §Clarifications/FR-012]
- [x] CHK018 上涨、震荡、下跌是否用总回报复权收益率、参考价格、到期价格、±1%/±3%/±6% 阈值和边界包含关系完整定义？[Measurability, Spec §FR-012]
- [x] CHK019 停牌、缺失到期价格或公司行动导致无法判定结果时，是否明确保持待验证而不静默延长、替换时点或改写预测？[Completeness, Spec §异常与边界场景, Spec §FR-027]
- [x] CHK020 预测概率的非负、100% ±0.1 个百分点容差、置信度、依据、风险、新鲜度、数据/特征/模型版本和固定免责声明是否都属于必填需求？[Completeness, Spec §FR-013/FR-014/FR-016, Contracts §预测契约]
- [x] CHK021 训练、验证、回测、特征、板块成员、复权、交易日历和汇率是否都被约束为预测时点已可获得的版本？[Completeness, Spec §FR-030, Research §R-005]
- [x] CHK022 时间滚动与扩展窗口的选择规则、标签观察期隔离、样本剔除和数据截点记录是否足以证明不存在未来数据泄漏？[Clarity, Research §R-005, Contracts §回测契约]

## 概率质量、回测与模型治理

- [x] CHK023 概率校准的衡量方式、报告粒度和合格口径是否与 Brier score、平衡准确率及三分类不均衡风险一致？[Ambiguity, Spec §FR-029/FR-032]
- [x] CHK024 简单基准是否定义为预先登记、版本化且与候选模型使用相同数据可得性、标签和成本假设？[Completeness, Spec §FR-029, Research §R-005]
- [x] CHK025 回测是否完整定义手续费、税费、滑点、最小交易单位、停牌、涨跌停、流动性、交易时段和不可成交的处理及报告口径？[Completeness, Research §R-005, Contracts §回测契约]
- [x] CHK026 概率预测质量与假设交易模拟表现是否明确分离，且后者不会被解释为收益承诺或交易建议？[Consistency, Research §R-005, Spec §FR-017]
- [x] CHK027 候选模型的 Brier score 改善 5%、平衡准确率增加 2 个百分点、单市场/周期退化不超过 2 个百分点、30 个交易日影子运行和严重故障定义是否均可客观审阅？[Measurability, Spec §FR-032/FR-033/SC-009]
- [x] CHK028 人工批准人、本机身份、批准理由、门禁证据、原子发布、失败阻断和回滚审计是否形成不可跳过且相互一致的生命周期要求？[Completeness, Spec §FR-033/FR-034, Data Model §状态机]

## MCP、Skill 与数字溯源

- [x] CHK029 通用契约是否为所有成功结果规定版本、请求/结果标识、市场数据截止时点、采集时间、数据版本、新鲜度、来源和警告字段？[Completeness, Contracts §通用契约]
- [x] CHK030 MCP 的本机边界、允许工具、非破坏性任务范围、禁止发布/回滚/删除/凭据/券商能力及拒绝错误是否无矛盾？[Consistency, Spec §FR-047/FR-048, Contracts §MCP 工具与权限契约]
- [x] CHK031 MCP 输入参数、分页、超时、资源限额、幂等键和工具版本演进规则是否在契约中明确到足以独立评审？[Gap, Contracts §通用契约, Contracts §MCP 工具与权限契约]
- [x] CHK032 大模型回答中每个量化数字的工具名、参数摘要、调用时间、结果标识、数据版本和预测/模型版本引用要求是否清楚？[Completeness, Spec §FR-019/FR-020, Research §R-007]
- [x] CHK033 工具超时、部分结果、权限拒绝、过期数据和契约错误时，大模型拒绝数字、用户可见说明与安全恢复动作是否一致定义？[Completeness, Spec §FR-020, Contracts §通用契约]
- [x] CHK034 每个 Skill 的允许工具、输入输出、超时、重试、失败码、步骤依赖和审计字段是否以版本化需求列出？[Gap, Research §R-007]

## 桌面体验、后台任务与恢复

- [x] CHK035 市场、板块、证券、预测、报告、模型、数据源和任务等关键页面是否分别定义空状态、加载状态、离线状态、权限受限状态和恢复路径？[Gap, Plan §每日调度、导入导出与性能基线]
- [x] CHK036 后台任务状态、取消、重试、去重、进度、部分成功、任务中断和重启恢复的用户可见语义是否完整且一致？[Completeness, Spec §FR-022/FR-025, Contracts §任务契约]
- [x] CHK037 桌面进程与后台/训练进程隔离、暂存结果不可见、提交后可见及崩溃不污染已验证数据的要求是否可追溯？[Completeness, Spec §FR-025, Plan §进程边界与数据流]
- [x] CHK038 4 核/16 GB/SSD 参考机、5 秒冷启动、2 秒查询 P95、100 毫秒交互 P95 和 1 秒状态可见的目标是否覆盖所有关键用户旅程或存在未量化页面？[Assumption, Plan §每日调度、导入导出与性能基线]

## 跨平台、存储与恢复边界

- [x] CHK039 Windows、macOS、Linux 的安装、升级、路径、权限、通知、文件锁、高 DPI、打包和恢复边界是否集中定义而非散落为隐含平台差异？[Completeness, Plan §项目结构/跨市场、错误降级与平台交付]
- [x] CHK040 三平台的 Windows 10/11、Apple Silicon/Intel、Ubuntu 22.04/24.04 覆盖范围及安装、启动、核心流程、升级、备份恢复验收是否明确？[Completeness, Plan §跨市场、错误降级与平台交付, Quickstart §打包验收]
- [x] CHK041 200 GB 预算、80% 门禁、15,000 证券、10 年日线、500 只两年分钟线的容量边界是否与不可删除快照、备份和非必要采集降级规则一致？[Consistency, Spec §FR-045/FR-046/SC-013]
- [x] CHK042 导入、普通导出、全量备份、恢复、可删除缓存/暂存和不可删除原始事实的用户权利、审计和可恢复性是否清楚？[Completeness, Plan §每日调度、导入导出与性能基线, Research §R-006]

## 中文规范、研究边界与风险披露

- [x] CHK043 项目自编写的规格、计划、任务、测试说明、使用说明、代码注释、文档字符串和示例的简体中文范围是否完整且可检查？[Completeness, Spec §FR-041, Constitution §XI]
- [x] CHK044 英文技术名词首次出现时的中文解释、第三方原文紧邻中文解释及禁止机械重复代码注释的要求是否与项目协作规范一致？[Consistency, Constitution §XI, AGENTS.md]
- [x] CHK045 券商连接、凭据、真实下单、撤单、自动交易、收益保证和确定性方向承诺是否在规格、计划、MCP 契约与报告要求中一律排除？[Consistency, Spec §FR-017/FR-040, Plan §宪法检查, Contracts §MCP 工具与权限契约]
- [x] CHK046 “研究参考，不构成投资建议”是否明确要求在预测界面、导出内容、报告、回测模拟和自然语言研究解释的相关产物中一致出现？[Completeness, Spec §FR-016/SC-012, Research §R-005]

## 评审记录

- 清单条目用于评估需求文本质量；勾选时应在评审记录中说明引用位置、发现的 Gap/Ambiguity/Conflict/Assumption，或提出规格修订建议。
- 本清单共 46 项；全部条目均带规格/计划/研究/数据模型引用或 Gap、Ambiguity、Conflict、Assumption 追踪标记。

### 2026-07-14 实施前复审

以下复审以“文档已给出可实施、可验收且无相互冲突的要求”为勾选条件；其中原有 Gap、
Ambiguity 与 Assumption 已通过本次契约、规格或任务修订关闭，未把它们转嫁给实现阶段。

| 条目 | 复审结论与证据 |
|---|---|
| CHK001–CHK006 | 通过：`research.md` R-003、`data-model.md` Market/Instrument/TradingCalendarVersion 与 `plan.md` 跨市场规则集中定义三市场身份、时区、日历、币种、汇率和公司行动版本。 |
| CHK007–CHK010 | 通过：`spec.md` FR-007–FR-011、`contracts/sectors.md` 与 `data-model.md` SectorMembershipVersion 定义板块来源、成员有效期、断裂阻断和轮动指标口径。 |
| CHK011–CHK016 | 通过：`spec.md` FR-042–FR-046、`research.md` R-006/R-008、`plan.md` 数据版本与错误降级；T015/T023 使凭据配置、重新授权与泄露拒绝具有先行测试和实现任务。 |
| CHK017–CHK022 | 通过：`spec.md` Clarifications、FR-012–FR-015/FR-030，`research.md` R-005，`contracts/predictions.md` 和 `contracts/backtests.md` 定义交易日标签、概率容差、快照边界、扩展/滚动窗口与数据截止时点。 |
| CHK023–CHK028 | 通过：`research.md` R-005、`spec.md` FR-029/FR-032–FR-034、`contracts/backtests.md`、`contracts/models.md` 明确概率校准、预登记简单基准、成本和不可成交约束、影子运行、人工批准与回滚。 |
| CHK029–CHK034 | 通过：`contracts/common.md` 与 `contracts/mcp-tools.md` 现已明确通用溯源、严格参数、分页、超时、资源限额、幂等、版本演进、Skill 允许工具、重试、失败码和审计字段。 |
| CHK035–CHK038 | 通过：T011 在任何页面实现前创建状态矩阵，T034/T043/T121 先测试并按矩阵实现与验证；`plan.md` 性能基线和 `contracts/tasks.md` 覆盖后台状态、隔离与恢复。 |
| CHK039–CHK042 | 通过：`research.md` R-006、`plan.md` 平台交付与导入导出策略、`data-model.md` BackupManifest 以及 T098–T106/T124–T126 定义三平台、容量和恢复边界。 |
| CHK043–CHK046 | 通过：宪法 XI、`spec.md` FR-016/FR-017/FR-040/FR-041、T008/T122/T127/T128 共同约束中文规范、研究边界、风险提示和发布审计。 |
