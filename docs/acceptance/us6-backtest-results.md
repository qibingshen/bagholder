# US6 历史验证与回测测试结果记录

## 记录范围

本记录对应 T097，用于固化回测契约、时间序列切分和不可成交失败场景测试结果。US6 只用于历史验证和研究复盘，不构成投资建议，不连接券商、不执行真实交易。

固定风险提示：研究参考，不构成投资建议。

## 指定测试命令

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_backtest_contract.py tests/property/test_time_series_backtest.py tests/failure/test_backtest_trading_constraints.py -q
```

## 执行结果

本次执行输出：`11 passed in 0.54s`，命令退出码为 0。

| 类别 | 文件 | 覆盖重点 | 当前结果 |
| --- | --- | --- | --- |
| 契约测试 | `tests/contract/test_backtest_contract.py` | 回测窗口、手续费、滑点、市场、周期、数据版本、模型版本、概率指标和简单基准比较 | 通过 |
| 时间序列测试 | `tests/property/test_time_series_backtest.py` | 滚动窗口、扩展窗口、标签观察期隔离和未来数据泄漏拒绝 | 通过 |
| 不可成交失败场景 | `tests/failure/test_backtest_trading_constraints.py` | 手续费、滑点、停牌、涨跌停、流动性不足、缺少不可成交约束数据 | 通过 |

## 验收结论

US6 当前满足：回测按时间序列切分，不使用预测时点之后的数据；回测结果保留版本链和简单基准比较；手续费、滑点、停牌、涨跌停、流动性和不可成交约束会阻断虚假成交。后续调整回测窗口、标签规则、成本模型或历史复盘页面时，必须重新运行本记录中的指定测试。
