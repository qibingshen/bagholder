# T042 最终复审包

## 提交

f9da692 fix: harden security research view facts

## 统计

 .superpowers/sdd/task-042-fix-report.md            |  32 +++++
 .../desktop/viewmodels/security_view_model.py      |  52 +++++--
 src/stock_agent/workers/market_ingestion.py        |  20 ++-
 tests/contract/test_market_data_contract.py        | 159 +++++++++++++++++++--
 4 files changed, 242 insertions(+), 21 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/task-042-fix-report.md b/.superpowers/sdd/task-042-fix-report.md
new file mode 100644
index 0000000..0b87166
--- /dev/null
+++ b/.superpowers/sdd/task-042-fix-report.md
@@ -0,0 +1,32 @@
+# T042 证券研究视图模型审查修复报告
+
+## 修复范围
+
+- 视图模型的日线字段改为直接接收采集链路真实产物 `IngestedHistoricalDailyBar`，不再使用 `MarketService` 中不兼容的平行日线模型。
+- 采集日线新增并强制保存 `artifact_version_id`；视图继续保留原有 `source_data_version`、来源和市场/采集时点。
+- `HistoricalFreshness` 仅接受 `HISTORICAL`，采集日线和视图模型均防御性拒绝其他新鲜度状态。
+- 当前预测准入同时要求交易日历为 `OPEN`、市场与采集时点可验证，以及既有新鲜度规则允许；`CLOSED` 和 `HOLIDAY` 一律为 `False`。
+- 指标、相对强弱和板块事实均新增 `security_id`，组装时发现任一事实跨证券即整批拒绝。
+- 空状态判定纳入相对强弱事实，只有相对强弱时不再显示“暂无事实”。
+
+## TDD 证据
+
+先在 `tests/contract/test_market_data_contract.py` 新增真实采集日线、历史新鲜度、交易日历、跨证券事实和相对强弱空状态的回归测试，再运行：
+
+```powershell
+pytest --no-cov tests/contract/test_market_data_contract.py -k "直接保留真实采集 or 拒绝被标记 or 交易日历未开市 or 另一证券 or 只存在相对强弱"
+```
+
+红灯结果为 `10 failed`：真实采集日线不能被 Pydantic 视图模型接收、非 `HISTORICAL` 状态未被拒绝、闭市/休市仍允许当前预测、跨证券衍生事实被渲染，以及仅有相对强弱时被误判为空状态。
+
+## 验证结果
+
+- `pytest --no-cov tests/contract/test_market_data_contract.py tests/integration/test_single_market_daily_pipeline.py`：`118 passed`。
+- `ruff check src/stock_agent/desktop/viewmodels/security_view_model.py src/stock_agent/workers/market_ingestion.py tests/contract/test_market_data_contract.py`：通过。
+- `ruff format --check src/stock_agent/desktop/viewmodels/security_view_model.py src/stock_agent/workers/market_ingestion.py tests/contract/test_market_data_contract.py`：通过。
+- `python tools/check_chinese_project_text.py src/stock_agent/desktop/viewmodels`、`src/stock_agent/workers` 和 `tests/contract`：通过。
+- 全量 `pytest --no-cov` 在收集阶段被既有缺失模块阻断：`tests/contract/test_desktop_state_contract.py` 导入 `stock_agent.desktop.pages.market_page` 失败；本任务未修改该页面模块。
+
+## 风险与回滚
+
+本次不连接网络、不生成预测数值，也不提供交易能力。若需回滚，可撤销本次对 `market_ingestion.py`、`security_view_model.py` 和对应契约测试的修改；采集工件版本字段是视图溯源完整性的必要契约。
diff --git a/src/stock_agent/desktop/viewmodels/security_view_model.py b/src/stock_agent/desktop/viewmodels/security_view_model.py
index 7c9b2b1..c349619 100644
--- a/src/stock_agent/desktop/viewmodels/security_view_model.py
+++ b/src/stock_agent/desktop/viewmodels/security_view_model.py
@@ -1,26 +1,28 @@
 """将本地已验证证券事实组装为桌面研究视图，不连接网络也不生成预测。"""
 
 from __future__ import annotations
 
 from datetime import datetime
 
 from pydantic import BaseModel, Field, model_validator
 
-from stock_agent.application.market_service import HistoricalDailyBar, MarketStatus
+from stock_agent.application.market_service import MarketStatus
 from stock_agent.domain.freshness import is_usable_for_current_prediction
 from stock_agent.domain.market import InstrumentIdentity
+from stock_agent.workers.market_ingestion import IngestedHistoricalDailyBar
 
 
 class _TraceableDerivedFact(BaseModel):
     """派生展示事实必须能定位到本地输入来源、时点和数据版本。"""
 
+    security_id: InstrumentIdentity
     source_id: str = Field(min_length=1)
     market_time: datetime
     collected_at: datetime
     input_data_version: str = Field(min_length=1)
     calculation_version: str = Field(min_length=1)
 
     @model_validator(mode="after")
     def 验证可追溯字段(self) -> _TraceableDerivedFact:
         """拒绝缺少审计时点或版本的派生数值。"""
 
@@ -41,20 +43,21 @@ class IndicatorFact(_TraceableDerivedFact):
 class RelativeStrengthFact(_TraceableDerivedFact):
     """相对强弱展示值及其输入、计算版本。"""
 
     value: float
     benchmark: str = Field(min_length=1)
 
 
 class SectorMembershipFact(BaseModel):
     """证券板块归属及其本地来源事实。"""
 
+    security_id: InstrumentIdentity
     sector_name: str = Field(min_length=1)
     source_id: str = Field(min_length=1)
     market_time: datetime
     collected_at: datetime
     data_version: str = Field(min_length=1)
 
     @model_validator(mode="after")
     def 验证可追溯字段(self) -> SectorMembershipFact:
         """拒绝缺少审计时点或版本的板块归属。"""
 
@@ -63,63 +66,78 @@ class SectorMembershipFact(BaseModel):
         if self.market_time > self.collected_at:
             raise ValueError("市场时间不能晚于采集时间")
         return self
 
 
 class SecurityResearchViewModel(BaseModel):
     """桌面证券研究页的只读事实视图模型。"""
 
     security_id: InstrumentIdentity
     market_status: MarketStatus | None
-    daily_bars: tuple[HistoricalDailyBar, ...] = ()
+    daily_bars: tuple[IngestedHistoricalDailyBar, ...] = ()
     indicators: tuple[IndicatorFact, ...] = ()
     sector_membership: SectorMembershipFact | None = None
     relative_strength: RelativeStrengthFact | None = None
     current_prediction_allowed: bool
     degradation_status_zh: str | None = None
     empty_state_zh: str | None = None
 
     @classmethod
     def assemble(
         cls,
         *,
         security_id: InstrumentIdentity,
         market_status: MarketStatus | None,
-        daily_bars: list[HistoricalDailyBar] | tuple[HistoricalDailyBar, ...] = (),
+        daily_bars: list[IngestedHistoricalDailyBar] | tuple[IngestedHistoricalDailyBar, ...] = (),
         indicators: list[IndicatorFact] | tuple[IndicatorFact, ...] = (),
         sector_membership: SectorMembershipFact | None = None,
         relative_strength: RelativeStrengthFact | None = None,
     ) -> SecurityResearchViewModel:
         """只组合调用方提供的本地事实；缺失事实保持为空，不补造任何数值。"""
 
         bars = tuple(daily_bars)
         indicator_values = tuple(indicators)
         if any(bar.security_id != security_id for bar in bars):
             raise ValueError("日线证券身份必须与研究证券一致")
+        if any(bar.freshness.state != "HISTORICAL" for bar in bars):
+            raise ValueError("历史日线新鲜度只能为 HISTORICAL")
+        if any(fact.security_id != security_id for fact in indicator_values):
+            raise ValueError("指标证券身份必须与研究证券一致")
+        if sector_membership is not None and sector_membership.security_id != security_id:
+            raise ValueError("板块事实证券身份必须与研究证券一致")
+        if relative_strength is not None and relative_strength.security_id != security_id:
+            raise ValueError("相对强弱证券身份必须与研究证券一致")
 
         if market_status is None:
             prediction_allowed = False
             degradation_status = "行情状态不可验证，已降级"
         else:
-            prediction_allowed = is_usable_for_current_prediction(
-                {
-                    "state": market_status.freshness.state,
-                    "market_time": market_status.market_time,
-                    "collected_at": market_status.collected_at,
-                    "time_is_verifiable": True,
-                }
+            prediction_allowed = (
+                market_status.trading_calendar_status == "OPEN"
+                and _时点可验证(market_status)
+                and is_usable_for_current_prediction(
+                    {
+                        "state": market_status.freshness.state,
+                        "market_time": market_status.market_time,
+                        "collected_at": market_status.collected_at,
+                        "time_is_verifiable": _时点可验证(market_status),
+                    }
+                )
             )
             degradation_status = _降级状态(market_status) if not prediction_allowed else None
 
         empty_state = (
             "暂无本地日K线、板块和指标事实"
-            if not bars and sector_membership is None and not indicator_values
+            if not bars
+            and sector_membership is None
+            and not indicator_values
+            and relative_strength is None
             else None
         )
 
         return cls(
             security_id=security_id,
             market_status=market_status,
             daily_bars=bars,
             indicators=indicator_values,
             sector_membership=sector_membership,
             relative_strength=relative_strength,
@@ -138,10 +156,22 @@ def _降级状态(market_status: MarketStatus) -> str:
         "CLOSED": "市场已闭市，已降级",
     }
     return labels.get(market_status.freshness.state, "行情状态不可验证，已降级")
 
 
 def _验证带时区时间(value: datetime, label: str) -> None:
     """确保展示来源时点可跨市场审计。"""
 
     if value.tzinfo is None or value.utcoffset() is None:
         raise ValueError(f"{label}必须包含时区")
+
+
+def _时点可验证(market_status: MarketStatus) -> bool:
+    """仅在市场和采集时点均带时区且顺序可审计时允许当前预测准入。"""
+
+    return (
+        market_status.market_time.tzinfo is not None
+        and market_status.market_time.utcoffset() is not None
+        and market_status.collected_at.tzinfo is not None
+        and market_status.collected_at.utcoffset() is not None
+        and market_status.market_time <= market_status.collected_at
+    )
diff --git a/src/stock_agent/workers/market_ingestion.py b/src/stock_agent/workers/market_ingestion.py
index ca5054a..7cbf9dc 100644
--- a/src/stock_agent/workers/market_ingestion.py
+++ b/src/stock_agent/workers/market_ingestion.py
@@ -1,46 +1,61 @@
 """通过注入读取器采集并原子保存中国市场历史日线。"""
 
 from __future__ import annotations
 
 import json
 from collections.abc import Callable
 from dataclasses import dataclass
 from datetime import datetime
-from typing import Any
+from typing import Any, Literal
 from uuid import uuid4
 
 from stock_agent.application.historical_market_data import (
     HistoricalDailyBar,
     HistoricalDailyBarBatch,
     HistoricalDailyBarValidationError,
 )
 from stock_agent.application.versioning_service import VersioningService
 from stock_agent.domain.market import InstrumentIdentity, Market
 
 
 class HistoricalDailyIngestionError(RuntimeError):
     """表示历史日线读取、验证或保存失败，且整个批次已回滚。"""
 
 
 @dataclass(frozen=True, slots=True)
 class HistoricalFreshness:
     """历史数据的新鲜度标识，明确排除实时用途。"""
 
-    state: str = "HISTORICAL"
+    state: Literal["HISTORICAL"] = "HISTORICAL"
+
+    def __post_init__(self) -> None:
+        """拒绝将历史日线伪装为实时、近实时或其他行情状态。"""
+
+        if self.state != "HISTORICAL":
+            raise ValueError("历史日线新鲜度只能为 HISTORICAL")
 
 
 @dataclass(frozen=True, slots=True)
 class IngestedHistoricalDailyBar(HistoricalDailyBar):
     """附带历史用途标识的标准化日线。"""
 
     freshness: HistoricalFreshness = HistoricalFreshness()
+    artifact_version_id: str = ""
+
+    def __post_init__(self) -> None:
+        """确保采集结果保留归一化工件版本并只作为历史事实使用。"""
+
+        if self.freshness.state != "HISTORICAL":
+            raise ValueError("历史日线新鲜度只能为 HISTORICAL")
+        if not self.artifact_version_id.strip():
+            raise ValueError("历史日线工件版本不能为空")
 
 
 @dataclass(frozen=True, slots=True)
 class HistoricalDailyIngestionResult:
     """一次可回读历史日线采集的版本链。"""
 
     bars: list[IngestedHistoricalDailyBar]
     raw_version_id: str
     normalized_version_id: str
 
@@ -185,20 +200,21 @@ class HistoricalDailyIngestionWorker:
                 open=bar.open,
                 high=bar.high,
                 low=bar.low,
                 close=bar.close,
                 volume=bar.volume,
                 currency=bar.currency,
                 adjustment_basis=bar.adjustment_basis,
                 source_id=bar.source_id,
                 collected_at=bar.collected_at,
                 source_data_version=bar.source_data_version,
+                artifact_version_id=normalized_version_id,
             )
             for bar in normalized
         ]
         document = {
             "source_id": source_id,
             "market": security_id.market.value,
             "security_code": security_id.display_code,
             "display_code": security_id.display_code,
             "exchange": security_id.exchange,
             "currency": security_id.currency,
diff --git a/tests/contract/test_market_data_contract.py b/tests/contract/test_market_data_contract.py
index bfb9191..0984221 100644
--- a/tests/contract/test_market_data_contract.py
+++ b/tests/contract/test_market_data_contract.py
@@ -1,12 +1,13 @@
 """验证行情适配器协议与注册表不依赖具体供应商。"""
 
+from dataclasses import replace
 from datetime import UTC, datetime, timedelta
 from zoneinfo import ZoneInfo
 
 import pytest
 from pydantic import ValidationError
 
 from stock_agent.adapters.market_data.base import (
     MarketDataAdapter,
     NormalizedQuote,
     SourceCapability,
@@ -24,20 +25,24 @@ from stock_agent.application.market_service import (
     MarketStatus,
 )
 from stock_agent.contracts.common import Freshness
 from stock_agent.desktop.viewmodels.security_view_model import (
     IndicatorFact,
     RelativeStrengthFact,
     SectorMembershipFact,
     SecurityResearchViewModel,
 )
 from stock_agent.domain.market import InstrumentIdentity, InstrumentIdentityInput, Market
+from stock_agent.workers.market_ingestion import (
+    HistoricalFreshness,
+    IngestedHistoricalDailyBar,
+)
 
 
 def 市场证券身份(market: Market) -> InstrumentIdentity:
     """构造仅用于契约测试的完整证券身份。"""
 
     exchange, display_code, currency = {
         Market.CN: ("SSE", "600000", "CNY"),
         Market.HK: ("HKEX", "00700", "HKD"),
         Market.US: ("NASDAQ", "AAPL", "USD"),
     }[market]
@@ -695,56 +700,56 @@ def test_各市场拒绝不符合本市场格式的证券代码(security_id: Ins
         ),
     ],
 )
 def test_市场身份拒绝交易所币种或代码不匹配(security_id: InstrumentIdentity) -> None:
     """市场、交易所、币种和代码必须构成一致身份，任一不匹配均应拒绝。"""
 
     with pytest.raises(ValueError):
         MarketService().validate_security_identity(security_id)
 
 
-def _完整日线() -> HistoricalDailyBar:
+def _完整日线() -> IngestedHistoricalDailyBar:
     """构造带完整本地溯源字段的历史日线事实。"""
 
-    return HistoricalDailyBar(
+    return IngestedHistoricalDailyBar(
         security_id=市场证券身份(Market.CN),
         trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
         open=10.0,
         high=10.5,
         low=9.8,
         close=10.2,
         volume=1_000_000,
         adjustment_basis="NONE",
         currency="CNY",
-        source_id="本地日线归档",
+        source_id="sina",
         market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
         collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
-        data_version="日线版本-7",
-        freshness=Freshness(state="CLOSED", age_seconds=0),
+        source_data_version="日线版本-7",
+        artifact_version_id="normalized-7",
     )
 
 
 def test_证券研究视图保留日线成交量及所有溯源信息() -> None:
     """K线和成交量必须直接展示本地事实，历史数据不可伪装为实时。"""
 
     bar = _完整日线()
     model = SecurityResearchViewModel.assemble(
         security_id=bar.security_id,
         market_status=MarketService().get_market_status(Market.CN),
         daily_bars=[bar],
     )
 
     assert model.daily_bars == (bar,)
     assert model.daily_bars[0].volume == 1_000_000
-    assert model.daily_bars[0].source_id == "本地日线归档"
-    assert model.daily_bars[0].data_version == "日线版本-7"
-    assert model.daily_bars[0].freshness.state != "REALTIME"
+    assert model.daily_bars[0].source_id == "sina"
+    assert model.daily_bars[0].source_data_version == "日线版本-7"
+    assert model.daily_bars[0].freshness.state == "HISTORICAL"
     assert model.empty_state_zh is None
 
 
 def test_证券研究视图拒绝缺少溯源版本的指标板块和相对强弱() -> None:
     """缺少来源、时点、输入版本或计算版本的派生事实不得渲染。"""
 
     with pytest.raises(ValidationError):
         IndicatorFact(
             name="MA5",
             value=10.1,
@@ -830,10 +835,148 @@ def test_证券研究视图在已验证近实时行情时允许当前预测() ->
         data_version="日历版本-1",
         freshness=Freshness(state="NEAR_REALTIME", age_seconds=0),
     )
 
     model = SecurityResearchViewModel.assemble(
         security_id=市场证券身份(Market.CN), market_status=status
     )
 
     assert model.current_prediction_allowed is True
     assert model.degradation_status_zh is None
+
+
+def _完整已采集历史日线() -> IngestedHistoricalDailyBar:
+    """构造真实采集链路使用的历史日线，包含来源版本和工件版本。"""
+
+    return IngestedHistoricalDailyBar(
+        security_id=市场证券身份(Market.CN),
+        trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
+        market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
+        open=10.0,
+        high=10.5,
+        low=9.8,
+        close=10.2,
+        volume=1_000_000,
+        currency="CNY",
+        adjustment_basis="NONE",
+        source_id="sina",
+        collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        source_data_version="sina-历史响应-7",
+        artifact_version_id="normalized-7",
+    )
+
+
+def test_证券研究视图直接保留真实采集历史日线的来源版本和工件版本() -> None:
+    """视图模型必须消费真实采集日线，不得改用不兼容的平行日线类型。"""
+
+    bar = _完整已采集历史日线()
+
+    model = SecurityResearchViewModel.assemble(
+        security_id=bar.security_id,
+        market_status=MarketService().get_market_status(Market.CN),
+        daily_bars=[bar],
+    )
+
+    assert model.daily_bars == (bar,)
+    assert model.daily_bars[0].source_data_version == "sina-历史响应-7"
+    assert hasattr(model.daily_bars[0], "artifact_version_id")
+    assert model.daily_bars[0].artifact_version_id == "normalized-7"
+    assert model.daily_bars[0].source_id == "sina"
+    assert model.daily_bars[0].freshness.state == "HISTORICAL"
+
+
+@pytest.mark.parametrize("state", ["REALTIME", "NEAR_REALTIME", "DELAYED", "STALE", "CLOSED"])
+def test_证券研究视图拒绝被标记为非历史新鲜度的采集日线(state: str) -> None:
+    """历史日线只能使用 HISTORICAL 新鲜度，不能伪装为实时或其他状态。"""
+
+    with pytest.raises(ValueError):
+        replace(_完整已采集历史日线(), freshness=HistoricalFreshness(state=state))
+
+
+@pytest.mark.parametrize("calendar_status", ["CLOSED", "HOLIDAY"])
+def test_证券研究视图在交易日历未开市时禁止当前预测(calendar_status: str) -> None:
+    """即使行情新鲜，闭市和休市也不具备当前预测的准入资格。"""
+
+    market_time = datetime(2026, 7, 14, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
+    status = MarketStatus(
+        market=Market.CN,
+        market_timezone="Asia/Shanghai",
+        trading_calendar_status=calendar_status,
+        market_time=market_time,
+        collected_at=market_time,
+        source_id="本地交易日历",
+        data_version="日历版本-1",
+        freshness=Freshness(state="REALTIME", age_seconds=0),
+    )
+
+    model = SecurityResearchViewModel.assemble(
+        security_id=市场证券身份(Market.CN), market_status=status
+    )
+
+    assert model.current_prediction_allowed is False
+
+
+def test_证券研究视图拒绝另一证券的指标相对强弱和板块事实() -> None:
+    """所有衍生事实都必须绑定当前证券，跨证券整批数据不得渲染。"""
+
+    other_security = 市场证券身份(Market.US)
+    market_time = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    indicator = IndicatorFact(
+        security_id=other_security,
+        name="MA5",
+        value=10.1,
+        source_id="本地指标输入",
+        market_time=market_time,
+        collected_at=market_time,
+        input_data_version="日线版本-7",
+        calculation_version="指标算法-1",
+    )
+    relative_strength = RelativeStrengthFact(
+        security_id=other_security,
+        value=0.8,
+        benchmark="沪深300",
+        source_id="本地相对强弱输入",
+        market_time=market_time,
+        collected_at=market_time,
+        input_data_version="日线版本-7",
+        calculation_version="相对强弱算法-1",
+    )
+    sector = SectorMembershipFact(
+        security_id=other_security,
+        sector_name="银行",
+        source_id="本地板块输入",
+        market_time=market_time,
+        collected_at=market_time,
+        data_version="板块版本-2",
+    )
+
+    with pytest.raises(ValueError):
+        SecurityResearchViewModel.assemble(
+            security_id=市场证券身份(Market.CN),
+            market_status=MarketService().get_market_status(Market.CN),
+            indicators=[indicator],
+            relative_strength=relative_strength,
+            sector_membership=sector,
+        )
+
+
+def test_证券研究视图只存在相对强弱事实时不显示无事实空状态() -> None:
+    """相对强弱是独立可渲染事实，不能被错误归类为全部事实缺失。"""
+
+    security_id = 市场证券身份(Market.CN)
+    market_time = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    model = SecurityResearchViewModel.assemble(
+        security_id=security_id,
+        market_status=MarketService().get_market_status(Market.CN),
+        relative_strength=RelativeStrengthFact(
+            security_id=security_id,
+            value=0.8,
+            benchmark="沪深300",
+            source_id="本地相对强弱输入",
+            market_time=market_time,
+            collected_at=market_time,
+            input_data_version="日线版本-7",
+            calculation_version="相对强弱算法-1",
+        ),
+    )
+
+    assert model.empty_state_zh is None

```

