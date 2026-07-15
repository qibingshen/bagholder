# T039：证券目录、市场状态与交易日历查询用例

## 目标

实现 T034 已批准的市场状态、证券目录和交易日历公开接口，使三市场时区、日历状态、来源与时点可以本地查询。

## 修改范围

- 新建：`src/stock_agent/application/market_service.py`
- 可修改：最小领域模型/测试文件以接入真实公开接口，不得删除 T034 已批准断言。

## 行为要求

1. 提供市场状态查询，覆盖 CN/HK/US，返回市场、明确时区、受控交易日历状态、市场时间、采集时间、来源和新鲜度；缺少市场/采集时间必须拒绝。
2. 提供证券身份目录查询/解析，明确处理 CN/HK/US 代码、交易所和币种；非唯一显示代码必须要求市场或交易所，不得猜测。
3. 仅从已验证本地数据/传入事实读取，不连接数据源；任何状态必须可追溯到来源、时点和版本。
4. 服务不产生预测、不把历史/延迟数据标为实时、不提供交易能力。

## TDD 与验证

T034/T036 的相关红灯已存在。先运行：

`py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py tests/failure/test_market_data_failures.py -v`

确认失败来自缺少 `market_service` / 身份解析接口，再最小实现；运行目标、组合、全量（如仍被页面模块收集阻断准确记录）、Ruff 与中文检查。报告写 `D:/personal/bagholder/.superpowers/sdd/task-039-report.md`，提交后仅回复提交、测试摘要、concerns。
