# US8 备份恢复测试结果记录

## 记录范围

本记录对应 T106，用于固化备份契约、容量预算和失败恢复测试结果。US8 仅覆盖本地数据、设置和任务状态的备份恢复，不备份凭据明文，不执行真实交易。

## 指定测试命令

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_backup_contract.py tests/property/test_storage_budget.py tests/failure/test_backup_recovery_failures.py -q
```

## 执行结果

本次执行输出：`9 passed in 0.52s`，命令退出码为 0。

| 类别 | 文件 | 覆盖重点 | 当前结果 |
| --- | --- | --- | --- |
| 备份契约 | `tests/contract/test_backup_contract.py` | 备份清单、SHA-256 哈希、版本链、平台信息、隔离恢复和原子切换 | 通过 |
| 容量预算 | `tests/property/test_storage_budget.py` | 200 GB 上限、80% 预警、分钟线保存上限和三平台路径适配 | 通过 |
| 失败恢复 | `tests/failure/test_backup_recovery_failures.py` | 损坏包拒绝、中断恢复、凭据排除和不可变工件删除拒绝 | 通过 |

## 验收结论

US8 当前满足：备份清单可校验，恢复必须隔离并经用户确认，凭据排除，容量门禁明确，不可变工件不得删除。后续调整备份清单、恢复路径、容量策略或删除影响确认时，必须重新运行本记录中的指定测试。
