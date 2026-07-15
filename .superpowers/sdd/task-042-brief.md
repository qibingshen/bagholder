# T042：证券研究视图模型

## 目标

实现本地证券研究视图模型，向桌面端提供 K 线、成交量、指标、所属板块、相对强弱及每项数值的来源/时点/版本。

## 修改范围

- 新建：`src/stock_agent/desktop/viewmodels/security_view_model.py`
- 新建或修改：对应契约测试，优先扩展 `tests/contract/test_market_data_contract.py`。

## TDD

先为以下公开模型/组装器写失败测试并运行：

1. 每根 K 线及成交量包含证券身份、交易日、OHLCV、币种、复权口径、来源、市场时间、采集时间、数据版本和新鲜度；禁止历史数据标为实时。
2. 指标值/相对强弱/板块归属均关联输入数据版本与计算版本，缺少来源/时点/版本即拒绝渲染。
3. 当前行情为 DELAYED/STALE/CLOSED/不可验证时，视图显示明确中文降级状态且 `current_prediction_allowed=False`，不得显示“实时”。
4. 无 K 线、无板块、无指标时模型显式给出空状态，不得虚构数值。

## 实现约束

- 只消费本地 `MarketService` 或已验证事实，不连接网络、不生成预测数值、不提供交易能力。
- 简体中文说明和文档字符串；数值保持可溯源。

## 验证

运行目标测试、全量 pytest（若页面模块仍缺失记录原因）、Ruff 与中文检查。报告 `D:/personal/bagholder/.superpowers/sdd/task-042-report.md`，提交后仅回复提交、测试摘要、concerns。
