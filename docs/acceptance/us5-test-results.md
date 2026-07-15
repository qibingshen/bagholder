# US5 每日任务与报告测试结果记录

## 记录范围

本记录对应 T088，用于固化每日调度、日报契约和任务恢复失败场景测试结果。US5 只覆盖本地研究任务和模拟报告，不连接券商、不执行真实交易。

固定风险提示：研究参考，不构成投资建议。

## 指定测试命令

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_daily_report_contract.py tests/property/test_market_scheduler.py tests/failure/test_daily_task_recovery.py -q
```

## 执行结果

本次执行输出：`11 passed in 0.50s`，命令退出码为 0。

| 类别 | 文件 | 覆盖重点 | 当前结果 |
| --- | --- | --- | --- |
| 契约测试 | `tests/contract/test_daily_report_contract.py` | 每日任务阶段、报告类型、状态机、日报快照、缺失范围、降级影响和固定风险提示 | 通过 |
| 调度数据测试 | `tests/property/test_market_scheduler.py` | A 股、港股、美股默认时点、休市、半日市和美股夏令时/冬令时 | 通过 |
| 失败场景测试 | `tests/failure/test_daily_task_recovery.py` | 源失败、限频、取消、中断、部分成功报告和降级通知 | 通过 |

## 验收结论

US5 当前满足：每日任务按市场日历和市场时区生成，源失败和限频不会伪装成完整成功，部分成功报告明确记录缺失范围和降级影响，取消或中断会保留恢复点。后续调整调度规则、日报章节、通知策略或任务恢复流程时，必须重新运行本记录中的指定测试。
