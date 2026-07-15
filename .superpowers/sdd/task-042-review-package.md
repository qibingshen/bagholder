# T042 审查包

## 提交

406d772 feat: add security research view model

## 统计

 .superpowers/sdd/task-042-report.md                |  35 +++++
 src/stock_agent/desktop/viewmodels/__init__.py     |   1 +
 .../desktop/viewmodels/security_view_model.py      | 147 +++++++++++++++++++++
 tests/contract/test_market_data_contract.py        | 143 ++++++++++++++++++++
 4 files changed, 326 insertions(+)

## 差异

```diff
diff --git a/.superpowers/sdd/task-042-report.md b/.superpowers/sdd/task-042-report.md
new file mode 100644
index 0000000..71fa817
--- /dev/null
+++ b/.superpowers/sdd/task-042-report.md
@@ -0,0 +1,35 @@
+# T042 证券研究视图模型报告
+
+## 实现说明
+
+新增 `src/stock_agent/desktop/viewmodels/security_view_model.py`，提供仅消费本地已验证事实的只读证券研究视图模型：
+
+- `SecurityResearchViewModel.assemble` 直接保留 `HistoricalDailyBar`，因此每根日 K 线及成交量同时保留证券身份、交易日、OHLCV、币种、复权口径、来源、市场时间、采集时间、数据版本和新鲜度；不连接网络、不补造数值、不提供交易能力。
+- `IndicatorFact`、`RelativeStrengthFact` 要求来源、市场时间、采集时间、输入数据版本和计算版本；`SectorMembershipFact` 要求来源、市场时间、采集时间和数据版本。缺任一必填溯源字段会由 Pydantic 拒绝。
+- `DELAYED`、`STALE`、`CLOSED` 或缺少市场状态时，显示明确中文降级提示并设置 `current_prediction_allowed=False`；已验证的 `REALTIME` / `NEAR_REALTIME` 事实沿用既有新鲜度规则。
+- 日 K 线、板块和指标均不存在时，返回明确空状态；不虚构价格、板块或指标。
+
+## TDD 证据
+
+先在 `tests/contract/test_market_data_contract.py` 增加视图模型公开契约。
+
+1. 首次运行 `pytest tests/contract/test_market_data_contract.py` 红灯：
+   `ModuleNotFoundError: No module named 'stock_agent.desktop.viewmodels'`，证明视图模型尚不存在。
+2. 实现最小视图模型后，为已验证近实时行情增加当前预测资格契约；运行
+   `pytest --no-cov tests/contract/test_market_data_contract.py -k "已验证近实时"` 红灯，断言实际得到 `False` 而期望 `True`。
+3. 仅向既有新鲜度规则传递已验证时点事实后复验。
+
+## 验证结果
+
+- `pytest --no-cov tests/contract/test_market_data_contract.py`：`92 passed in 0.50s`。
+- `ruff check src/stock_agent/desktop/viewmodels/security_view_model.py tests/contract/test_market_data_contract.py`：通过。
+- `ruff format --check src/stock_agent/desktop/viewmodels/security_view_model.py tests/contract/test_market_data_contract.py`：通过。
+- `python tools/check_chinese_project_text.py src/stock_agent/desktop/viewmodels`：通过。
+- 全量 `pytest --no-cov` 在收集阶段被既有缺失页面模块阻断：
+  `ModuleNotFoundError: No module named 'stock_agent.desktop.pages.market_page'`，来源为 `tests/contract/test_desktop_state_contract.py`，与本任务视图模型无关。
+- 全仓 `ruff check .` 未通过，既有问题位于 `tests/contract/test_desktop_state_contract.py` 与 `tools/check_chinese_project_text.py`。
+- 全仓中文检查未通过，既有问题位于 `tests/failure/test_market_data_failures.py:88`，提示“注释缺少简体中文解释”。本任务新增源文件的中文检查通过。
+
+## 回滚策略
+
+若需要回滚，只需删除本任务新增的 `desktop/viewmodels` 包，并还原 `test_market_data_contract.py` 中的证券研究视图契约；不会影响网络、预测、下单或交易路径。
diff --git a/src/stock_agent/desktop/viewmodels/__init__.py b/src/stock_agent/desktop/viewmodels/__init__.py
new file mode 100644
index 0000000..c2a002d
--- /dev/null
+++ b/src/stock_agent/desktop/viewmodels/__init__.py
@@ -0,0 +1 @@
+"""桌面端视图模型。"""
diff --git a/src/stock_agent/desktop/viewmodels/security_view_model.py b/src/stock_agent/desktop/viewmodels/security_view_model.py
new file mode 100644
index 0000000..7c9b2b1
--- /dev/null
+++ b/src/stock_agent/desktop/viewmodels/security_view_model.py
@@ -0,0 +1,147 @@
+"""将本地已验证证券事实组装为桌面研究视图，不连接网络也不生成预测。"""
+
+from __future__ import annotations
+
+from datetime import datetime
+
+from pydantic import BaseModel, Field, model_validator
+
+from stock_agent.application.market_service import HistoricalDailyBar, MarketStatus
+from stock_agent.domain.freshness import is_usable_for_current_prediction
+from stock_agent.domain.market import InstrumentIdentity
+
+
+class _TraceableDerivedFact(BaseModel):
+    """派生展示事实必须能定位到本地输入来源、时点和数据版本。"""
+
+    source_id: str = Field(min_length=1)
+    market_time: datetime
+    collected_at: datetime
+    input_data_version: str = Field(min_length=1)
+    calculation_version: str = Field(min_length=1)
+
+    @model_validator(mode="after")
+    def 验证可追溯字段(self) -> _TraceableDerivedFact:
+        """拒绝缺少审计时点或版本的派生数值。"""
+
+        _验证带时区时间(self.market_time, "市场时间")
+        _验证带时区时间(self.collected_at, "采集时间")
+        if self.market_time > self.collected_at:
+            raise ValueError("市场时间不能晚于采集时间")
+        return self
+
+
+class IndicatorFact(_TraceableDerivedFact):
+    """指标展示值及其输入、计算版本。"""
+
+    name: str = Field(min_length=1)
+    value: float
+
+
+class RelativeStrengthFact(_TraceableDerivedFact):
+    """相对强弱展示值及其输入、计算版本。"""
+
+    value: float
+    benchmark: str = Field(min_length=1)
+
+
+class SectorMembershipFact(BaseModel):
+    """证券板块归属及其本地来源事实。"""
+
+    sector_name: str = Field(min_length=1)
+    source_id: str = Field(min_length=1)
+    market_time: datetime
+    collected_at: datetime
+    data_version: str = Field(min_length=1)
+
+    @model_validator(mode="after")
+    def 验证可追溯字段(self) -> SectorMembershipFact:
+        """拒绝缺少审计时点或版本的板块归属。"""
+
+        _验证带时区时间(self.market_time, "市场时间")
+        _验证带时区时间(self.collected_at, "采集时间")
+        if self.market_time > self.collected_at:
+            raise ValueError("市场时间不能晚于采集时间")
+        return self
+
+
+class SecurityResearchViewModel(BaseModel):
+    """桌面证券研究页的只读事实视图模型。"""
+
+    security_id: InstrumentIdentity
+    market_status: MarketStatus | None
+    daily_bars: tuple[HistoricalDailyBar, ...] = ()
+    indicators: tuple[IndicatorFact, ...] = ()
+    sector_membership: SectorMembershipFact | None = None
+    relative_strength: RelativeStrengthFact | None = None
+    current_prediction_allowed: bool
+    degradation_status_zh: str | None = None
+    empty_state_zh: str | None = None
+
+    @classmethod
+    def assemble(
+        cls,
+        *,
+        security_id: InstrumentIdentity,
+        market_status: MarketStatus | None,
+        daily_bars: list[HistoricalDailyBar] | tuple[HistoricalDailyBar, ...] = (),
+        indicators: list[IndicatorFact] | tuple[IndicatorFact, ...] = (),
+        sector_membership: SectorMembershipFact | None = None,
+        relative_strength: RelativeStrengthFact | None = None,
+    ) -> SecurityResearchViewModel:
+        """只组合调用方提供的本地事实；缺失事实保持为空，不补造任何数值。"""
+
+        bars = tuple(daily_bars)
+        indicator_values = tuple(indicators)
+        if any(bar.security_id != security_id for bar in bars):
+            raise ValueError("日线证券身份必须与研究证券一致")
+
+        if market_status is None:
+            prediction_allowed = False
+            degradation_status = "行情状态不可验证，已降级"
+        else:
+            prediction_allowed = is_usable_for_current_prediction(
+                {
+                    "state": market_status.freshness.state,
+                    "market_time": market_status.market_time,
+                    "collected_at": market_status.collected_at,
+                    "time_is_verifiable": True,
+                }
+            )
+            degradation_status = _降级状态(market_status) if not prediction_allowed else None
+
+        empty_state = (
+            "暂无本地日K线、板块和指标事实"
+            if not bars and sector_membership is None and not indicator_values
+            else None
+        )
+
+        return cls(
+            security_id=security_id,
+            market_status=market_status,
+            daily_bars=bars,
+            indicators=indicator_values,
+            sector_membership=sector_membership,
+            relative_strength=relative_strength,
+            current_prediction_allowed=prediction_allowed,
+            degradation_status_zh=degradation_status,
+            empty_state_zh=empty_state,
+        )
+
+
+def _降级状态(market_status: MarketStatus) -> str:
+    """将不可用于当前预测的行情状态转换为明确中文提示。"""
+
+    labels = {
+        "DELAYED": "行情延迟，已降级",
+        "STALE": "行情过期，已降级",
+        "CLOSED": "市场已闭市，已降级",
+    }
+    return labels.get(market_status.freshness.state, "行情状态不可验证，已降级")
+
+
+def _验证带时区时间(value: datetime, label: str) -> None:
+    """确保展示来源时点可跨市场审计。"""
+
+    if value.tzinfo is None or value.utcoffset() is None:
+        raise ValueError(f"{label}必须包含时区")
diff --git a/tests/contract/test_market_data_contract.py b/tests/contract/test_market_data_contract.py
index 23e54dd..bfb9191 100644
--- a/tests/contract/test_market_data_contract.py
+++ b/tests/contract/test_market_data_contract.py
@@ -17,20 +17,26 @@ from stock_agent.adapters.market_data.registry import (
     SourceCapabilityViolationError,
     UnknownSourceError,
 )
 from stock_agent.application.market_service import (
     HistoricalDailyBar,
     InstrumentCatalogEntry,
     MarketService,
     MarketStatus,
 )
 from stock_agent.contracts.common import Freshness
+from stock_agent.desktop.viewmodels.security_view_model import (
+    IndicatorFact,
+    RelativeStrengthFact,
+    SectorMembershipFact,
+    SecurityResearchViewModel,
+)
 from stock_agent.domain.market import InstrumentIdentity, InstrumentIdentityInput, Market
 
 
 def 市场证券身份(market: Market) -> InstrumentIdentity:
     """构造仅用于契约测试的完整证券身份。"""
 
     exchange, display_code, currency = {
         Market.CN: ("SSE", "600000", "CNY"),
         Market.HK: ("HKEX", "00700", "HKD"),
         Market.US: ("NASDAQ", "AAPL", "USD"),
@@ -687,10 +693,147 @@ def test_各市场拒绝不符合本市场格式的证券代码(security_id: Ins
         InstrumentIdentityInput(
             market=Market.US, exchange="NASDAQ", display_code="600000", currency="USD"
         ),
     ],
 )
 def test_市场身份拒绝交易所币种或代码不匹配(security_id: InstrumentIdentity) -> None:
     """市场、交易所、币种和代码必须构成一致身份，任一不匹配均应拒绝。"""
 
     with pytest.raises(ValueError):
         MarketService().validate_security_identity(security_id)
+
+
+def _完整日线() -> HistoricalDailyBar:
+    """构造带完整本地溯源字段的历史日线事实。"""
+
+    return HistoricalDailyBar(
+        security_id=市场证券身份(Market.CN),
+        trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
+        open=10.0,
+        high=10.5,
+        low=9.8,
+        close=10.2,
+        volume=1_000_000,
+        adjustment_basis="NONE",
+        currency="CNY",
+        source_id="本地日线归档",
+        market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
+        collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        data_version="日线版本-7",
+        freshness=Freshness(state="CLOSED", age_seconds=0),
+    )
+
+
+def test_证券研究视图保留日线成交量及所有溯源信息() -> None:
+    """K线和成交量必须直接展示本地事实，历史数据不可伪装为实时。"""
+
+    bar = _完整日线()
+    model = SecurityResearchViewModel.assemble(
+        security_id=bar.security_id,
+        market_status=MarketService().get_market_status(Market.CN),
+        daily_bars=[bar],
+    )
+
+    assert model.daily_bars == (bar,)
+    assert model.daily_bars[0].volume == 1_000_000
+    assert model.daily_bars[0].source_id == "本地日线归档"
+    assert model.daily_bars[0].data_version == "日线版本-7"
+    assert model.daily_bars[0].freshness.state != "REALTIME"
+    assert model.empty_state_zh is None
+
+
+def test_证券研究视图拒绝缺少溯源版本的指标板块和相对强弱() -> None:
+    """缺少来源、时点、输入版本或计算版本的派生事实不得渲染。"""
+
+    with pytest.raises(ValidationError):
+        IndicatorFact(
+            name="MA5",
+            value=10.1,
+            source_id="本地指标输入",
+            market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
+            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            input_data_version="日线版本-7",
+            calculation_version="",
+        )
+
+    with pytest.raises(ValidationError):
+        SectorMembershipFact(
+            sector_name="银行",
+            source_id="",
+            market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
+            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            data_version="板块版本-2",
+        )
+
+    with pytest.raises(ValidationError):
+        RelativeStrengthFact(
+            value=0.8,
+            benchmark="沪深300",
+            source_id="本地相对强弱输入",
+            market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
+            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            input_data_version="日线版本-7",
+            calculation_version="",
+        )
+
+
+@pytest.mark.parametrize("state", ["DELAYED", "STALE", "CLOSED"])
+def test_证券研究视图为非实时状态显示中文降级并禁止当前预测(state: str) -> None:
+    """延迟、过期或闭市事实必须明确降级，且永不声称实时。"""
+
+    market_time = datetime(2026, 7, 14, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
+    status = MarketStatus(
+        market=Market.CN,
+        market_timezone="Asia/Shanghai",
+        trading_calendar_status="CLOSED",
+        market_time=market_time,
+        collected_at=market_time,
+        source_id="本地交易日历",
+        data_version="日历版本-1",
+        freshness=Freshness(state=state, age_seconds=0),
+    )
+
+    model = SecurityResearchViewModel.assemble(
+        security_id=市场证券身份(Market.CN), market_status=status
+    )
+
+    assert model.current_prediction_allowed is False
+    assert model.degradation_status_zh
+    assert "实时" not in model.degradation_status_zh
+
+
+def test_证券研究视图在没有日线板块和指标时明确为空状态() -> None:
+    """本地事实缺失时展示空状态，不能补造价格、板块或指标数值。"""
+
+    model = SecurityResearchViewModel.assemble(
+        security_id=市场证券身份(Market.CN),
+        market_status=MarketService().get_market_status(Market.CN),
+    )
+
+    assert model.daily_bars == ()
+    assert model.indicators == ()
+    assert model.sector_membership is None
+    assert model.relative_strength is None
+    assert model.empty_state_zh
+
+
+def test_证券研究视图在已验证近实时行情时允许当前预测() -> None:
+    """已验证的近实时本地行情应保留当前预测资格，而非被错误降级。"""
+
+    market_time = datetime(2026, 7, 14, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
+    status = MarketStatus(
+        market=Market.CN,
+        market_timezone="Asia/Shanghai",
+        trading_calendar_status="OPEN",
+        market_time=market_time,
+        collected_at=market_time,
+        source_id="本地交易日历",
+        data_version="日历版本-1",
+        freshness=Freshness(state="NEAR_REALTIME", age_seconds=0),
+    )
+
+    model = SecurityResearchViewModel.assemble(
+        security_id=市场证券身份(Market.CN), market_status=status
+    )
+
+    assert model.current_prediction_allowed is True
+    assert model.degradation_status_zh is None

```

