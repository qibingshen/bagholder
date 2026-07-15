# US4 板块测试结果记录

## 记录范围

本记录对应 T078，用于固化板块契约、成员历史和失败场景测试结果。US4 只覆盖研究展示、模拟分析和历史复核，不连接券商、不执行真实交易。

固定风险提示：研究参考，不构成投资建议。

## 指定测试命令

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_sector_contract.py tests/property/test_sector_membership_history.py tests/failure/test_sector_failures.py -q
```

## 执行结果

本次执行输出：`9 passed in 0.52s`，命令退出码为 0。

| 类别 | 文件 | 覆盖重点 | 当前结果 |
| --- | --- | --- | --- |
| 契约测试 | `tests/contract/test_sector_contract.py` | 板块分类、市场、币种、成员有效期、指标字段、覆盖率和自定义板块变更契约 | 通过 |
| 成员历史测试 | `tests/property/test_sector_membership_history.py` | 成员增删历史、点时成员查询、跨市场证券键和追加式审计序列 | 通过 |
| 失败场景测试 | `tests/failure/test_sector_failures.py` | 成员历史断裂、覆盖率不足、禁止误导性排名和跨市场不可比较阻断 | 通过 |

## 验收结论

US4 当前满足：成员有效期可表达，自定义板块成员历史追加保存，历史分析按时间点查询，覆盖率不足和成员历史断裂时会阻断误导性排名。后续如调整板块指标、轮动算法、页面降级或跨市场比较规则，必须重新运行本记录中的指定测试。
