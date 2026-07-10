# 板块与自定义板块契约

## 查询

`sector.list`、`sector.get_metrics`、`sector.get_rotation`、`custom_sector.get`、
`custom_sector.get_members_at` 返回板块来源、成员有效时间、覆盖率、涨跌、成交活跃度、
上涨下跌家数、趋势和轮动。历史请求必须提供分析市场时间并固定成员关系版本。

## 管理

桌面端可创建、重命名、归档自定义板块及添加/移除成员。每次变更新增成员关系版本，包含
`valid_from`、`valid_to`、来源、操作者和审计事件；禁止更新历史成员行。成员历史不完整时，
历史指标返回 `DATA_INCOMPLETE`，不得生成排名。
