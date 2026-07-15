# T036 后续：市场数据拒绝原因与公司行动规则

## 目标

使已批准的 `tests/failure/test_market_data_failures.py` 的 9 个红灯转绿，不改变 T041 已批准的布尔型 `is_usable_for_current_prediction` 契约。

## 当前失败

1. `DELAYED`、`STALE`、`CLOSED` 与时点不可验证的当前预测必须产生可解释的领域拒绝原因；现有布尔函数返回 False 但不提供原因。
2. `CompanyAction` 缺少 `adjustment_ratio`、证券身份与市场字段及校验。
3. `require_company_actions_for_adjustment` 尚未实现，无法在复权历史研究缺失行动记录时明确阻断。

## 约束与最小实现

1. 保持 `is_usable_for_current_prediction` 返回 bool；新增明确的强制准入函数（或等价公开入口），在不可用时抛 `FreshnessClassificationError`，错误信息说明“过期/休市/时点不可验证”等原因。不要让调用方通过状态字符串绕过时点校验。
2. 扩展 `CompanyAction`：`adjustment_ratio` 必须为有限且大于零；若同时提供 `security_id` 与 `market`，二者必须一致；有效时间必须带时区；保留既有字段兼容性。
3. 在 `market_rules.py` 实现 `require_company_actions_for_adjustment`：调整研究需要行动记录而列表为空时抛现有的时点/领域违规异常，错误说明“公司行动缺失/不可用”；不得生成或猜测行动数据。
4. 测试必须先确认当前 9 项失败，再作最小实现。所有项目文字中文；不增加外部数据、预测数值、券商或交易。

## 验证

运行 `py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -v` 至全绿；再运行相关新鲜度/公司行动测试、全量 pytest、Ruff 和中文检查。报告写入 `D:/personal/bagholder/.superpowers/sdd/t036-rule-implementation-report.md`，提交后仅回复提交、测试摘要、concerns。
