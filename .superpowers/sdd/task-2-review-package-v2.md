# 任务 2 复核包（修复后）

## 提交
d5c86cf fix: tighten sina code validation
d67b9b1 docs: add task 2 report
29ecc09 feat: enforce freshness and sina code rules

## 统计
 .superpowers/sdd/task-2-report.md                  | 82 ++++++++++++++++++
 src/stock_agent/adapters/market_data/sina_codes.py | 25 ++++++
 src/stock_agent/domain/freshness.py                | 51 +++++++++++
 tests/failure/test_market_data_failures.py         | 41 +++++++++
 tests/property/test_freshness_rules.py             | 99 ++++++++++++++++++++++
 5 files changed, 298 insertions(+)

## 差异
diff --git a/.superpowers/sdd/task-2-report.md b/.superpowers/sdd/task-2-report.md
new file mode 100644
index 0000000..dc1d53d
--- /dev/null
+++ b/.superpowers/sdd/task-2-report.md
@@ -0,0 +1,82 @@
+# Task 2 完成报告：新鲜度与新浪代码规则
+
+## 范围与文件
+
+- `src/stock_agent/domain/freshness.py`：跨市场新鲜度纯分类规则。
+- `src/stock_agent/adapters/market_data/sina_codes.py`：新浪 A 股请求代码纯规范化规则。
+- `tests/property/test_freshness_rules.py`：新鲜度阈值、休市和时间错误测试。
+- `tests/failure/test_market_data_failures.py`：新浪代码合法映射与拒绝测试。
+
+未实现 HTTP、供应商响应解析、存储、凭据、券商、下单或自动交易功能。
+
+## TDD 证据
+
+1. 先新增两份测试文件并执行指定 pytest 命令。
+2. 初次执行在收集阶段失败：`ModuleNotFoundError`，缺少
+   `stock_agent.domain.freshness` 与
+   `stock_agent.adapters.market_data.sina_codes`，证明测试先于实现存在。
+3. 写入最小纯规则实现后，补充“休市时优先返回 `CLOSED`”测试；该测试先因
+   `FreshnessClassificationError` 失败，再将休市分支移动到时间校验之前。
+4. 最终指定测试全部通过。
+
+## 验证证据
+
+执行时间：2026-07-14。
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py -v
+```
+
+结果：`21 passed in 0.67s`。
+
+```powershell
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+```
+
+结果：格式检查显示 `53 files already formatted`，静态检查退出码为 0 且无诊断。
+
+## 自检
+
+- CN 在 5 秒、HK/US 在 15 秒仍为 `REALTIME`，超限为 `NEAR_REALTIME`。
+- 60 秒为 `NEAR_REALTIME`，61 秒至 900 秒为 `DELAYED`，901 秒为 `STALE`。
+- 休市一律为 `CLOSED`；开市时无时区与负年龄均抛出领域错误。
+- 仅 CN 的 SSE/SZSE 六位数字代码映射为 `sh`/`sz` 前缀；其他市场、交易所和代码均拒绝。
+- 已执行暂存差异空白检查，任务实现提交未包含范围外文件。
+
+## 提交哈希
+
+- `29ecc09863bb448f10e8acc262f805d8dc0973e9`：`feat: enforce freshness and sina code rules`
+
+## Concerns
+
+- 无已知功能性 concern。
+- 工作区中存在其他代理或用户的未跟踪、已修改文件；本任务提交未包含它们。
+
+## 复核修复记录
+
+### 修复内容
+
+- 新浪代码六位校验改为逐字符严格 ASCII `0-9` 判断，不再接受 Unicode 十进制数字。
+- 新鲜度测试补充 CN/HK/US 开市时年龄为 0 秒的 `REALTIME` 边界。
+- 新鲜度测试补充 `collected_at` 无时区时必须拒绝的场景。
+- 新浪代码拒绝测试补充全角数字 `１２３４５６`。
+
+### 复核 TDD 证据
+
+新增全角数字拒绝用例后，指定 pytest 命令先失败：该用例未抛出
+`UnsupportedSinaCodeError`，原因是原实现使用 `isdecimal()` 接受全角数字。收紧
+ASCII 校验后，指定 pytest 命令通过。
+
+### 复核验证证据
+
+执行时间：2026-07-14。
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+```
+
+结果：`26 passed in 0.58s`；格式检查显示 `53 files already formatted`；静态检查退出码为
+0 且无诊断。
diff --git a/src/stock_agent/adapters/market_data/sina_codes.py b/src/stock_agent/adapters/market_data/sina_codes.py
new file mode 100644
index 0000000..454ed0f
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/sina_codes.py
@@ -0,0 +1,25 @@
+"""定义新浪 A 股请求代码的纯规范化规则。"""
+
+from __future__ import annotations
+
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+class UnsupportedSinaCodeError(ValueError):
+    """表示证券身份不能安全转换为新浪 A 股请求代码。"""
+
+
+def normalize_sina_code(identity: InstrumentIdentity) -> str:
+    """将沪深 A 股六码数字代码转换为新浪请求前缀格式。"""
+
+    if identity.market is not Market.CN:
+        raise UnsupportedSinaCodeError("新浪代码规则只支持中国市场")
+    if len(identity.display_code) != 6 or any(
+        character < "0" or character > "9" for character in identity.display_code
+    ):
+        raise UnsupportedSinaCodeError("新浪代码必须是六位数字")
+
+    prefix = {"SSE": "sh", "SZSE": "sz"}.get(identity.exchange)
+    if prefix is None:
+        raise UnsupportedSinaCodeError("新浪代码不支持该交易所")
+    return f"{prefix}{identity.display_code}"
diff --git a/src/stock_agent/domain/freshness.py b/src/stock_agent/domain/freshness.py
new file mode 100644
index 0000000..a38221a
--- /dev/null
+++ b/src/stock_agent/domain/freshness.py
@@ -0,0 +1,51 @@
+"""集中定义跨市场行情新鲜度的纯分类规则。"""
+
+from __future__ import annotations
+
+from datetime import datetime
+
+from stock_agent.contracts.common import FreshnessState
+from stock_agent.domain.market import Market
+
+
+class FreshnessClassificationError(ValueError):
+    """表示无法安全计算行情新鲜度的时间错误。"""
+
+
+def classify_freshness(
+    market: Market,
+    market_time: datetime,
+    collected_at: datetime,
+    is_open: bool,
+) -> FreshnessState:
+    """按市场时点、采集时点和开市状态返回兼容公共契约的新鲜度。"""
+
+    if not is_open:
+        return "CLOSED"
+
+    _validate_times(market_time, collected_at)
+
+    age_seconds = (collected_at - market_time).total_seconds()
+    realtime_limit = 5 if market is Market.CN else 15
+    if age_seconds <= realtime_limit:
+        return "REALTIME"
+    if age_seconds <= 60:
+        return "NEAR_REALTIME"
+    if age_seconds <= 900:
+        return "DELAYED"
+    return "STALE"
+
+
+def _validate_times(market_time: datetime, collected_at: datetime) -> None:
+    """拒绝无时区或市场时点晚于采集时点的时间组合。"""
+
+    if not _is_aware(market_time) or not _is_aware(collected_at):
+        raise FreshnessClassificationError("市场时间和采集时间必须包含时区")
+    if market_time > collected_at:
+        raise FreshnessClassificationError("市场时间不能晚于采集时间")
+
+
+def _is_aware(value: datetime) -> bool:
+    """返回时间是否带有可用 UTC 偏移。"""
+
+    return value.tzinfo is not None and value.utcoffset() is not None
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
new file mode 100644
index 0000000..c4c0707
--- /dev/null
+++ b/tests/failure/test_market_data_failures.py
@@ -0,0 +1,41 @@
+"""验证新浪代码规则拒绝不安全或不受支持的身份。"""
+
+import pytest
+
+from stock_agent.adapters.market_data.sina_codes import (
+    UnsupportedSinaCodeError,
+    normalize_sina_code,
+)
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+@pytest.mark.parametrize(
+    ("exchange", "display_code", "expected"),
+    [("SSE", "600000", "sh600000"), ("SZSE", "000001", "sz000001")],
+)
+def test_新浪代码规范化支持沪深交易所(exchange: str, display_code: str, expected: str) -> None:
+    """新浪 A 股请求代码必须携带正确交易所前缀。"""
+
+    identity = InstrumentIdentity(Market.CN, exchange, display_code, "CNY")
+
+    assert normalize_sina_code(identity) == expected
+
+
+@pytest.mark.parametrize(
+    "identity",
+    [
+        InstrumentIdentity(Market.HK, "HKEX", "00001", "HKD"),
+        InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD"),
+        InstrumentIdentity(Market.CN, "BSE", "830000", "CNY"),
+        InstrumentIdentity(Market.CN, "SSE", "60000", "CNY"),
+        InstrumentIdentity(Market.CN, "SZSE", "0000A1", "CNY"),
+        InstrumentIdentity(Market.CN, "SSE", "１２３４５６", "CNY"),
+    ],
+)
+def test_新浪代码规范化拒绝跨市场交易所和非法代码(
+    identity: InstrumentIdentity,
+) -> None:
+    """非中国市场、非沪深交易所或非六码数字代码一律拒绝。"""
+
+    with pytest.raises(UnsupportedSinaCodeError):
+        normalize_sina_code(identity)
diff --git a/tests/property/test_freshness_rules.py b/tests/property/test_freshness_rules.py
new file mode 100644
index 0000000..192947a
--- /dev/null
+++ b/tests/property/test_freshness_rules.py
@@ -0,0 +1,99 @@
+"""验证跨市场行情新鲜度的纯规则边界。"""
+
+from datetime import UTC, datetime, timedelta
+
+import pytest
+
+from stock_agent.domain.freshness import FreshnessClassificationError, classify_freshness
+from stock_agent.domain.market import Market
+
+
+@pytest.mark.parametrize(
+    ("market", "realtime_limit"),
+    [
+        (Market.CN, 0),
+        (Market.HK, 0),
+        (Market.US, 0),
+        (Market.CN, 5),
+        (Market.HK, 15),
+        (Market.US, 15),
+    ],
+)
+def test_交易时段在各市场实时精确边界内为实时(market: Market, realtime_limit: int) -> None:
+    """各市场年龄等于实时阈值时仍应判为实时行情。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    market_time = collected_at - timedelta(seconds=realtime_limit)
+
+    assert classify_freshness(market, market_time, collected_at, is_open=True) == "REALTIME"
+
+
+@pytest.mark.parametrize(
+    ("market", "age_seconds"),
+    [(Market.CN, 6), (Market.HK, 16), (Market.US, 16)],
+)
+def test_交易时段超过各市场实时边界为近实时(market: Market, age_seconds: int) -> None:
+    """实时阈值之外且不超过一分钟的行情应降为近实时。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    market_time = collected_at - timedelta(seconds=age_seconds)
+
+    assert classify_freshness(market, market_time, collected_at, is_open=True) == "NEAR_REALTIME"
+
+
+@pytest.mark.parametrize(
+    ("age_seconds", "expected"),
+    [(60, "NEAR_REALTIME"), (61, "DELAYED"), (900, "DELAYED"), (901, "STALE")],
+)
+def test_交易时段通用时效边界(age_seconds: int, expected: str) -> None:
+    """一分钟与十五分钟边界必须保持与公共新鲜度契约一致。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    market_time = collected_at - timedelta(seconds=age_seconds)
+
+    assert classify_freshness(Market.CN, market_time, collected_at, is_open=True) == expected
+
+
+def test_休市时忽略时间年龄并返回休市() -> None:
+    """休市行情不能被标为可实时使用。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+
+    assert (
+        classify_freshness(Market.US, collected_at - timedelta(days=1), collected_at, is_open=False)
+        == "CLOSED"
+    )
+
+
+def test_休市时即使市场时间异常也返回休市() -> None:
+    """休市状态优先于时间年龄，避免下游把休市行情当成可用行情。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+
+    assert (
+        classify_freshness(
+            Market.CN, collected_at + timedelta(seconds=1), collected_at, is_open=False
+        )
+        == "CLOSED"
+    )
+
+
+@pytest.mark.parametrize(
+    ("market_time", "collected_at"),
+    [
+        (datetime(2026, 7, 14, 9, 30), datetime(2026, 7, 14, 9, 30, tzinfo=UTC)),
+        (
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            datetime(2026, 7, 14, 9, 30),
+        ),
+        (
+            datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        ),
+    ],
+)
+def test_拒绝无时区或负年龄的时间(market_time: datetime, collected_at: datetime) -> None:
+    """无时区和未来市场时间都不能伪装成新鲜行情。"""
+
+    with pytest.raises(FreshnessClassificationError):
+        classify_freshness(Market.CN, market_time, collected_at, is_open=True)
