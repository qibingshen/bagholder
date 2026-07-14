# T040 原子可见性第四轮修复报告

## 修复结果

- `VersioningService.version_exists()` 不再以工件自身 `_COMPLETE` 作为独立发布依据。
- 所有版本（包括 `commit_bytes()` 的单工件兼容调用）只有在所属 `.batches/<batch_id>/_COMPLETE` 写入后才可通过 `version_exists()`、`read_bytes()` 和 `metadata_for()` 查询。
- 当进程在工件 `_COMPLETE` 与批次 `_COMPLETE` 之间中断时，版本保持不可见；下次服务启动会通过未完成批次恢复清理工件目录和元数据。
- 增加主 journal 为 `{"entries":[]}` 且没有 batch index 的恢复回归，确认恢复仍以 `recovery.json` 清单清理残留。

## TDD 证据

先新增“单工件在所属批次公开前不可见”测试，模拟批次完成标记写入抛出异常且回滚未执行。旧实现红灯：`version_exists("daily-bars", "v1")` 错误返回 `True`。移除工件自身完成标记的独立可见性路径后转绿。

## 验证结果

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py -q
# 11 passed

py -3.12 -m pytest -o addopts='' tests/integration/test_versioning_atomic_commit.py tests/integration/test_sina_market_data_provenance.py tests/integration/test_single_market_daily_pipeline.py -q
# 36 passed

py -3.12 -m ruff format --check src/stock_agent/application/versioning_service.py tests/integration/test_versioning_atomic_commit.py
py -3.12 -m ruff check src/stock_agent/application/versioning_service.py tests/integration/test_versioning_atomic_commit.py
py -3.12 tools/check_chinese_project_text.py
```

上述格式、静态和中文检查均通过。

## 风险与边界

调用方必须经由 `VersioningService` 的查询接口读取已发布版本；直接扫描工件目录不属于该服务可见性契约。包含 `tests/failure/test_market_data_failures.py` 的组合命令有 14 项既有失败，涉及新鲜度分类、跨市场证券身份与公司行动规则，不涉及本次版本发布路径。
