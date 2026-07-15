# T034：市场数据与桌面状态契约测试

## 目标

为用户故事 US1 新增契约测试，在实现市场服务与桌面页面前锁定可验收行为。

## 修改范围

- 修改：`tests/contract/test_market_data_contract.py`
- 新建：`tests/contract/test_desktop_state_contract.py`

## 必须先新增并运行失败的测试

1. 市场状态查询契约：A 股、港股、美股的市场状态必须至少含市场标识、市场时区、交易日历状态、市场时间、采集时间、数据来源和新鲜度；市场时间或采集时间缺失时拒绝。
2. 历史日线查询契约：每条日线至少含证券身份、交易日、开高低收、成交量、复权口径、币种、来源、市场时间、采集时间和数据版本；不得把历史日线标为实时；起止日期非法或跨市场证券代码不匹配时拒绝。
3. 页面状态契约：市场页和个股页需要能表达空、加载、离线、权限受限、过期、恢复以及可用状态；每个状态必须含用户可见中文说明，离线/过期状态不得显示实时或可用于当前预测。

## 约束

- 仅写测试，禁止新增生产实现文件；测试应预期未来由 `market_service.py`、`market_page.py` 和 `security_page.py` 提供的最小公开接口。
- 先运行新增测试并记录明确的失败原因（预期为模块/接口缺失或断言失败），不能为了通过而在测试中内嵌实现。
- 测试文件的说明、文档字符串和断言说明使用简体中文。
- 不添加数据源 HTTP、券商、下单或交易能力。

## 验证与报告

运行 `py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py tests/contract/test_desktop_state_contract.py -v`，确认新增需求在实现前失败；在 `D:/personal/bagholder/.superpowers/sdd/task-034-report.md` 记录新增用例、失败证据、命令与输出摘要。提交测试和报告。仅返回提交、测试摘要和 concerns。
