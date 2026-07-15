# T036 复审包

## 提交

1360d35 test: add market data failure coverage

## 统计

 .superpowers/sdd/task-036-report.md        |  37 +++++
 tests/failure/test_market_data_failures.py | 210 ++++++++++++++++++++++++++++-
 2 files changed, 246 insertions(+), 1 deletion(-)

## 差异

```diff
diff --git a/.superpowers/sdd/task-036-report.md b/.superpowers/sdd/task-036-report.md
new file mode 100644
index 0000000..e8c6160
--- /dev/null
+++ b/.superpowers/sdd/task-036-report.md
@@ -0,0 +1,37 @@
+# T036 市场数据失败场景测试报告
+
+## 新增用例
+
+- 日线原始字段缺失：覆盖开高低收、成交量、交易日期、市场时间、币种、复权口径、来源、采集时间和数据版本；要求整批拒绝，且 `market-data-raw` 与 `market-data-normalized` 均不产生记录。
+- 当前预测：覆盖 `DELAYED`、`STALE`、`CLOSED` 与市场时间不可验证；要求拒绝并显式给出“过期”或“不可用”原因。
+- 证券解析：覆盖 A/H/美股的交易所与币种不一致，要求拒绝猜测或跨市场混用。
+- 公司行动：覆盖不合法复权比例、缺失标识、无时区日期、证券与市场不一致；同时确认原始行情与预测快照的同版本写入不能静默覆盖。
+
+## 红灯验证
+
+执行命令：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -v
+```
+
+实际结果：`26 failed, 24 passed in 12.86s`，退出码为 `1`，已确认红灯。
+
+失败摘要：
+
+- 缺少公开的标准化历史日线批次契约；测试直接以 `trading_date`、`market_time`、开高低收、成交量、币种、复权口径、来源、采集时间和数据版本构造数据，不依赖新浪原始响应的字段位置。
+- `DELAYED`、`STALE`、`CLOSED` 与市场时间不可验证目前仅返回裸布尔拒绝，未提供“过期”或“不可用”的显式状态/错误。
+- `InstrumentIdentity` 当前接受市场、交易所和币种不一致的组合。
+- 缺少不带市场标识时解析非唯一显示代码的公开接口；测试模拟 `000001` 同时存在于深市和港交所并要求拒绝。
+- `CompanyAction` 尚无复权比例及证券/市场归属字段，也缺少公司行动记录不存在时阻断复权历史研究的公开接口。
+
+## 审查补充
+
+- 已移除对新浪响应中无语义字段位置的假设，改为标准化历史日线与批次持久化契约测试。
+- 已新增同一显示代码跨两个市场的非唯一查询拒绝测试。
+- 已新增公司行动记录为空时复权历史研究必须明确拒绝的测试；保留原有空 `action_id` 校验作为记录字段完整性的独立场景。
+
+## 范围确认
+
+- 仅修改 `tests/failure/test_market_data_failures.py` 并新增本报告。
+- 未修改 `src/`，未新增 HTTP、券商、下单或交易能力。
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
index 8738db4..b2e3aaf 100644
--- a/tests/failure/test_market_data_failures.py
+++ b/tests/failure/test_market_data_failures.py
@@ -3,22 +3,27 @@
 from datetime import UTC, datetime
 from pathlib import Path
 
 import pytest
 
 from stock_agent.adapters.market_data.sina_adapter import SinaDataSourceError, SinaHttpAdapter
 from stock_agent.adapters.market_data.sina_codes import (
     UnsupportedSinaCodeError,
     normalize_sina_code,
 )
-from stock_agent.application.versioning_service import VersioningService
+from stock_agent.application.versioning_service import ImmutableVersionError, VersioningService
+from stock_agent.domain.freshness import (
+    FreshnessClassificationError,
+    is_usable_for_current_prediction,
+)
 from stock_agent.domain.market import InstrumentIdentity, Market
+from stock_agent.domain.market_rules import CompanyAction
 
 
 class 忽略事实记录器:
     """隔离响应校验测试的记录端口，不替代持久化集成测试。"""
 
     def record(self, raw_response: bytes, quotes: list[object]) -> None:
         """响应校验失败路径不会调用该端口。"""
 
 
 def 新浪响应(日期: str, 时间: str) -> bytes:
@@ -99,10 +104,213 @@ def test_新浪适配器拒绝异常或不完整响应且不返回部分行情(
 
 def test_新浪适配器响应缺少任一请求代码时拒绝全部行情(local_data_root: Path) -> None:
     """多证券响应缺行时不能泄露已成功解析的部分结果。"""
 
     response = 新浪响应("2026-07-14", "09:30:00")
 
     with pytest.raises(SinaDataSourceError):
         SinaHttpAdapter(
             lambda _url: response, 忽略事实记录器(), VersioningService(local_data_root)
         ).fetch_quotes(["sh600000", "sz000001"], datetime(2026, 7, 14, 1, 30, tzinfo=UTC))
+
+
+@pytest.mark.parametrize(
+    "缺失字段",
+    [
+        "trading_date",
+        "market_time",
+        "open",
+        "high",
+        "low",
+        "close",
+        "volume",
+        "currency",
+        "adjustment_basis",
+        "source_id",
+        "collected_at",
+        "data_version",
+    ],
+)
+def test_标准化历史日线缺少任一契约字段时整批拒绝且不产生持久化记录(
+    缺失字段: str, local_data_root: Path
+) -> None:
+    """以公开标准化日线契约校验字段，不依赖特定供应商原始响应位置。"""
+
+    from stock_agent.application.historical_market_data import (
+        HistoricalDailyBarBatch,
+        HistoricalDailyBarValidationError,
+    )
+
+    完整日线 = {
+        "security_id": InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
+        "trading_date": "2026-07-14",
+        "market_time": datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
+        "open": 10.0,
+        "high": 10.3,
+        "low": 9.9,
+        "close": 10.2,
+        "volume": 1000,
+        "currency": "CNY",
+        "adjustment_basis": "none",
+        "source_id": "test-source",
+        "collected_at": datetime(2026, 7, 14, 15, 1, tzinfo=UTC),
+        "data_version": "daily-v1",
+    }
+    不完整日线 = 完整日线.copy()
+    del 不完整日线[缺失字段]
+
+    批次 = HistoricalDailyBarBatch(VersioningService(local_data_root))
+    with pytest.raises(HistoricalDailyBarValidationError, match="缺失|完整"):
+        批次.normalize_and_save([完整日线, 不完整日线])
+
+    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
+    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
+
+
+@pytest.mark.parametrize("状态", ["DELAYED", "STALE", "CLOSED"])
+def test_当前预测拒绝过期或休市行情并给出不可用原因(状态: str) -> None:
+    """当前预测入口必须把不可用原因显式反馈给调用方，不能只返回裸布尔值。"""
+
+    with pytest.raises(FreshnessClassificationError, match="过期|不可用"):
+        is_usable_for_current_prediction(
+            {
+                "state": 状态,
+                "market_time": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+                "collected_at": datetime(2026, 7, 14, 9, 16, tzinfo=UTC),
+                "time_is_verifiable": True,
+            }
+        )
+
+
+def test_当前预测拒绝市场时间不可验证行情并给出不可用原因() -> None:
+    """即使状态标为实时，市场时间不可验证也必须明确拒绝当前预测。"""
+
+    with pytest.raises(FreshnessClassificationError, match="不可验证|不可用"):
+        is_usable_for_current_prediction(
+            {
+                "state": "REALTIME",
+                "market_time": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+                "collected_at": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+                "time_is_verifiable": False,
+            }
+        )
+
+
+@pytest.mark.parametrize(
+    ("market", "exchange", "display_code", "currency"),
+    [
+        (Market.CN, "HKEX", "00001", "CNY"),
+        (Market.HK, "NASDAQ", "AAPL", "HKD"),
+        (Market.US, "SSE", "600000", "USD"),
+        (Market.HK, "HKEX", "00001", "USD"),
+    ],
+)
+def test_证券身份拒绝市场交易所或币种不一致(
+    market: Market, exchange: str, display_code: str, currency: str
+) -> None:
+    """A、H、美股解析不得把相同代码、错误交易所或错误币种猜测为有效证券。"""
+
+    with pytest.raises(ValueError, match="市场|交易所|币种"):
+        InstrumentIdentity(market, exchange, display_code, currency)
+
+
+def test_未带市场标识的非唯一显示代码必须拒绝解析() -> None:
+    """同一显示代码存在于多个市场时，查询必须要求调用方提供市场或交易所。"""
+
+    from stock_agent.domain.market import MarketRuleError, resolve_instrument_identity
+
+    候选证券 = [
+        InstrumentIdentity(Market.CN, "SZSE", "000001", "CNY"),
+        InstrumentIdentity(Market.HK, "HKEX", "000001", "HKD"),
+    ]
+
+    with pytest.raises(MarketRuleError, match="市场|交易所|非唯一"):
+        resolve_instrument_identity(display_code="000001", candidates=候选证券)
+
+
+@pytest.mark.parametrize("复权比例", [0, -1, float("inf")])
+def test_公司行动拒绝不合法复权比例(复权比例: float) -> None:
+    """复权比例必须为有限正数，不能让无效公司行动进入历史价格计算。"""
+
+    with pytest.raises(ValueError, match="复权比例"):
+        CompanyAction(
+            action_id="split-20260714",
+            action_type="split",
+            effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+            version_id="v1",
+            source_id="test-source",
+            adjustment_ratio=复权比例,
+        )
+
+
+@pytest.mark.parametrize(
+    ("action_id", "effective_at"),
+    [
+        ("", datetime(2026, 7, 14, 9, 0, tzinfo=UTC)),
+        ("split-20260714", datetime(2026, 7, 14, 9, 0)),
+    ],
+)
+def test_公司行动拒绝缺失标识或无时区日期(
+    action_id: str, effective_at: datetime
+) -> None:
+    """公司行动的标识和生效时点均是可追溯复权的最小前提。"""
+
+    with pytest.raises(ValueError, match="标识|时区"):
+        CompanyAction(
+            action_id=action_id,
+            action_type="split",
+            effective_at=effective_at,
+            version_id="v1",
+            source_id="test-source",
+        )
+
+
+def test_公司行动拒绝证券所属市场不一致() -> None:
+    """公司行动必须绑定与证券身份一致的市场，不能跨市场混用。"""
+
+    with pytest.raises(ValueError, match="证券|市场"):
+        CompanyAction(
+            action_id="split-20260714",
+            action_type="split",
+            effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+            version_id="v1",
+            source_id="test-source",
+            security_id=InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
+            market=Market.US,
+        )
+
+
+def test_复权历史研究在公司行动记录缺失时明确拒绝() -> None:
+    """缺少应有的公司行动记录时，复权历史研究不能输出看似可用的结果。"""
+
+    from stock_agent.domain.market_rules import (
+        PointInTimeViolation,
+        require_company_actions_for_adjustment,
+    )
+
+    with pytest.raises(PointInTimeViolation, match="公司行动.*缺失|不可用"):
+        require_company_actions_for_adjustment(
+            security_id=InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
+            analysis_time=datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
+            actions=[],
+        )
+
+
+@pytest.mark.parametrize("dataset", ["market-data-raw", "prediction-snapshots"])
+def test_原始行情和预测快照拒绝静默覆盖(dataset: str, local_data_root: Path) -> None:
+    """相同版本标识重写必须失败，保留可追溯的既有事实。"""
+
+    service = VersioningService(local_data_root)
+    service.commit_bytes(
+        dataset=dataset,
+        version_id="v1",
+        content=b"first",
+        source_id="test-source",
+    )
+
+    with pytest.raises(ImmutableVersionError):
+        service.commit_bytes(
+            dataset=dataset,
+            version_id="v1",
+            content=b"overwrite",
+            source_id="test-source",
+        )

```

