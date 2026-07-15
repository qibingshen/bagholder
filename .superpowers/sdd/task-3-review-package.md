# 任务 3 复核包

## 提交
331f1be feat: add sina a-share market data adapter

## 统计
 .superpowers/sdd/task-3-report.md                  |  49 ++++++++
 .../adapters/market_data/sina_adapter.py           | 130 +++++++++++++++++++++
 tests/failure/test_market_data_failures.py         |  54 +++++++++
 .../test_single_market_daily_pipeline.py           |  38 ++++++
 4 files changed, 271 insertions(+)

## 差异
diff --git a/.superpowers/sdd/task-3-report.md b/.superpowers/sdd/task-3-report.md
new file mode 100644
index 0000000..d0fdfdf
--- /dev/null
+++ b/.superpowers/sdd/task-3-report.md
@@ -0,0 +1,49 @@
+# Task 3 新浪 HTTP 适配器报告
+
+## 变更文件
+
+- `src/stock_agent/adapters/market_data/sina_adapter.py`
+- `tests/integration/test_single_market_daily_pipeline.py`
+- `tests/failure/test_market_data_failures.py`
+
+## 实现摘要
+
+- 新增只读 `SinaHttpAdapter`，仅通过注入的 `http_get` 发起受控新浪 HTTP GET。
+- 严格校验请求代码、GBK 响应、响应行、必要字段和日期时间；任一失败均抛出 `SinaDataSourceError`，不返回部分行情。
+- 将沪深代码映射为 `Market.CN` 证券身份，以 `Asia/Shanghai` 构造市场时间，并调用 `classify_freshness` 生成新鲜度。
+- 以原始响应的 SHA-256 生成非空新浪数据版本标识。
+
+## TDD 证据
+
+先新增适配器导入与边界测试，再运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
+```
+
+首次运行在收集阶段失败，原因是 `ModuleNotFoundError: No module named 'stock_agent.adapters.market_data.sina_adapter'`，证明测试覆盖了尚未实现的接口。完成最小实现后，同一命令通过 21 项测试。
+
+## 验证命令
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+最终验证结果：21 passed；Ruff 格式检查通过；Ruff 静态检查通过；差异空白检查通过。
+
+## 自检
+
+- 未访问真实网络，测试读取器均为本地注入函数。
+- 未实现历史日线、复权、公司行为、存储、凭据、券商、订单或自动交易能力。
+- 未修改任务范围外的项目文件；工作区中既有的其他未提交变更未纳入本任务。
+
+## 提交
+
+本报告随提交 `feat: add sina a-share market data adapter` 一并提交；最终哈希以 Git 当前提交为准。
+
+## Concerns
+
+无。
diff --git a/src/stock_agent/adapters/market_data/sina_adapter.py b/src/stock_agent/adapters/market_data/sina_adapter.py
new file mode 100644
index 0000000..41358d4
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/sina_adapter.py
@@ -0,0 +1,130 @@
+"""提供只读新浪 A 股行情 HTTP 适配器。"""
+
+from __future__ import annotations
+
+import hashlib
+import math
+import re
+from collections.abc import Callable
+from datetime import datetime
+from zoneinfo import ZoneInfo
+
+from stock_agent.adapters.market_data.base import NormalizedQuote, SourceCapability
+from stock_agent.contracts.common import Freshness
+from stock_agent.domain.freshness import classify_freshness
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+_SINA_URL_PREFIX = "http://hq.sinajs.cn/list="
+_SINA_CODE_PATTERN = re.compile(r"(?P<prefix>sh|sz)(?P<display_code>[0-9]{6})\Z")
+_SINA_LINE_PATTERN = re.compile(
+    r'var hq_str_(?P<code>sh[0-9]{6}|sz[0-9]{6})="(?P<fields>[^"]*)";\Z'
+)
+_SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
+
+
+class SinaDataSourceError(RuntimeError):
+    """表示新浪读取结果无法安全转换为完整规范化行情。"""
+
+
+class SinaHttpAdapter:
+    """通过调用方注入的读取器获取并验证新浪 A 股实时报价。"""
+
+    capability = SourceCapability(
+        source_id="sina",
+        markets=(Market.CN.value,),
+        credential_required=False,
+        supports_realtime=True,
+    )
+
+    def __init__(self, http_get: Callable[[str], bytes]) -> None:
+        """保存受控 HTTP GET 读取器，适配器自身不创建网络连接。"""
+
+        self._http_get = http_get
+
+    def fetch_quotes(self, codes: list[str], collected_at: datetime) -> list[NormalizedQuote]:
+        """读取全部请求代码；任一异常均拒绝返回部分行情。"""
+
+        self._validate_codes(codes)
+        url = f"{_SINA_URL_PREFIX}{','.join(codes)}"
+        try:
+            raw_response = self._http_get(url)
+            if not isinstance(raw_response, bytes):
+                raise TypeError("HTTP 读取器必须返回字节串")
+            decoded_response = raw_response.decode("gbk")
+            parsed_fields = self._parse_response(decoded_response, codes)
+            data_version = f"sina-{hashlib.sha256(raw_response).hexdigest()}"
+            return [
+                self._normalize_quote(code, parsed_fields[code], collected_at, data_version)
+                for code in codes
+            ]
+        except SinaDataSourceError:
+            raise
+        except Exception as error:
+            raise SinaDataSourceError("新浪行情响应无效，拒绝生成量化行情") from error
+
+    @staticmethod
+    def _validate_codes(codes: list[str]) -> None:
+        if not codes or any(_SINA_CODE_PATTERN.fullmatch(code) is None for code in codes):
+            raise SinaDataSourceError("新浪请求代码必须为 sh 或 sz 加六位 ASCII 数字")
+        if len(set(codes)) != len(codes):
+            raise SinaDataSourceError("新浪请求代码不能重复")
+
+    @staticmethod
+    def _parse_response(response: str, codes: list[str]) -> dict[str, list[str]]:
+        if not response.strip():
+            raise SinaDataSourceError("新浪响应不能为空")
+
+        parsed: dict[str, list[str]] = {}
+        lines = [line.strip() for line in response.splitlines() if line.strip()]
+        for line in lines:
+            match = _SINA_LINE_PATTERN.fullmatch(line)
+            if match is None:
+                raise SinaDataSourceError("新浪响应格式错误")
+            code = match.group("code")
+            if code not in codes or code in parsed:
+                raise SinaDataSourceError("新浪响应包含未请求或重复的证券代码")
+            fields = match.group("fields").split(",")
+            if len(fields) <= 31 or not fields[0].strip():
+                raise SinaDataSourceError("新浪响应缺少证券名称或关键字段")
+            parsed[code] = fields
+
+        if set(parsed) != set(codes):
+            raise SinaDataSourceError("新浪响应缺少请求的证券行情")
+        return parsed
+
+    @staticmethod
+    def _normalize_quote(
+        code: str,
+        fields: list[str],
+        collected_at: datetime,
+        data_version: str,
+    ) -> NormalizedQuote:
+        try:
+            price = float(fields[3])
+            if not math.isfinite(price):
+                raise ValueError("价格必须为有限数值")
+            market_time = datetime.strptime(
+                f"{fields[30].strip()} {fields[31].strip()}", "%Y-%m-%d %H:%M:%S"
+            ).replace(tzinfo=_SHANGHAI_TIMEZONE)
+            freshness_state = classify_freshness(Market.CN, market_time, collected_at, is_open=True)
+            age_seconds = int((collected_at - market_time).total_seconds())
+            match = _SINA_CODE_PATTERN.fullmatch(code)
+            if match is None:
+                raise ValueError("响应代码格式错误")
+            exchange = "SSE" if match.group("prefix") == "sh" else "SZSE"
+            return NormalizedQuote(
+                security_id=InstrumentIdentity(
+                    market=Market.CN,
+                    exchange=exchange,
+                    display_code=match.group("display_code"),
+                    currency="CNY",
+                ),
+                price=price,
+                source_id="sina",
+                market_time=market_time,
+                collected_at=collected_at,
+                data_version=data_version,
+                freshness=Freshness(state=freshness_state, age_seconds=age_seconds),
+            )
+        except Exception as error:
+            raise SinaDataSourceError("新浪响应包含无法使用的价格或市场时间") from error
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
index c4c0707..26da636 100644
--- a/tests/failure/test_market_data_failures.py
+++ b/tests/failure/test_market_data_failures.py
@@ -1,21 +1,31 @@
 """验证新浪代码规则拒绝不安全或不受支持的身份。"""
 
+from datetime import UTC, datetime
+
 import pytest
 
+from stock_agent.adapters.market_data.sina_adapter import SinaDataSourceError, SinaHttpAdapter
 from stock_agent.adapters.market_data.sina_codes import (
     UnsupportedSinaCodeError,
     normalize_sina_code,
 )
 from stock_agent.domain.market import InstrumentIdentity, Market
 
 
+def 新浪响应(日期: str, 时间: str) -> bytes:
+    """构造字段数量完整的单条新浪响应，供失败边界覆盖使用。"""
+
+    fields = ["浦发银行", "10.00", "10.10", "10.25", *("0" for _ in range(26)), 日期, 时间, "00"]
+    return f'var hq_str_sh600000="{",".join(fields)}";'.encode("gbk")
+
+
 @pytest.mark.parametrize(
     ("exchange", "display_code", "expected"),
     [("SSE", "600000", "sh600000"), ("SZSE", "000001", "sz000001")],
 )
 def test_新浪代码规范化支持沪深交易所(exchange: str, display_code: str, expected: str) -> None:
     """新浪 A 股请求代码必须携带正确交易所前缀。"""
 
     identity = InstrumentIdentity(Market.CN, exchange, display_code, "CNY")
 
     assert normalize_sina_code(identity) == expected
@@ -32,10 +42,54 @@ def test_新浪代码规范化支持沪深交易所(exchange: str, display_code:
         InstrumentIdentity(Market.CN, "SSE", "１２３４５６", "CNY"),
     ],
 )
 def test_新浪代码规范化拒绝跨市场交易所和非法代码(
     identity: InstrumentIdentity,
 ) -> None:
     """非中国市场、非沪深交易所或非六码数字代码一律拒绝。"""
 
     with pytest.raises(UnsupportedSinaCodeError):
         normalize_sina_code(identity)
+
+
+@pytest.mark.parametrize("codes", [[], ["600000"], ["sh60000"], ["xx600000"], ["sh６０００００"]])
+def test_新浪适配器拒绝空或非法请求代码(codes: list[str]) -> None:
+    """请求代码必须已是沪深前缀加六码 ASCII 数字，避免构造越界地址。"""
+
+    with pytest.raises(SinaDataSourceError):
+        SinaHttpAdapter(lambda _url: b"").fetch_quotes(codes, datetime.now(UTC))
+
+
+@pytest.mark.parametrize(
+    "response",
+    [
+        RuntimeError("网络故障"),
+        b"\xff",
+        'var hq_str_sh600000="浦发银行,10.00";'.encode("gbk"),
+        'var hq_str_sh600000="浦发银行,abc,10.10,无效";'.encode("gbk"),
+        新浪响应("2026-02-30", "09:30:00"),
+        新浪响应("2026-07-14", "25:30:00"),
+    ],
+)
+def test_新浪适配器拒绝异常或不完整响应且不返回部分行情(response: bytes | Exception) -> None:
+    """读取、解码、字段和市场时间任一异常都必须作为数据源错误整体失败。"""
+
+    def 读取行情(_url: str) -> bytes:
+        if isinstance(response, Exception):
+            raise response
+        return response
+
+    with pytest.raises(SinaDataSourceError):
+        SinaHttpAdapter(读取行情).fetch_quotes(
+            ["sh600000"], datetime(2026, 7, 14, 1, 30, tzinfo=UTC)
+        )
+
+
+def test_新浪适配器响应缺少任一请求代码时拒绝全部行情() -> None:
+    """多证券响应缺行时不能泄露已成功解析的部分结果。"""
+
+    response = 新浪响应("2026-07-14", "09:30:00")
+
+    with pytest.raises(SinaDataSourceError):
+        SinaHttpAdapter(lambda _url: response).fetch_quotes(
+            ["sh600000", "sz000001"], datetime(2026, 7, 14, 1, 30, tzinfo=UTC)
+        )
diff --git a/tests/integration/test_single_market_daily_pipeline.py b/tests/integration/test_single_market_daily_pipeline.py
new file mode 100644
index 0000000..20499bd
--- /dev/null
+++ b/tests/integration/test_single_market_daily_pipeline.py
@@ -0,0 +1,38 @@
+"""验证新浪 A 股行情适配器的受控请求与规范化输出。"""
+
+from datetime import UTC, datetime
+
+from stock_agent.adapters.market_data.sina_adapter import SinaHttpAdapter
+from stock_agent.domain.market import Market
+
+
+def test_新浪适配器以精确地址读取_GBK_行情并保留完整溯源信息() -> None:
+    """适配器只能使用约定地址，并将合法响应转为可量化使用的完整行情。"""
+
+    requested_urls: list[str] = []
+    response = (
+        'var hq_str_sh600000="浦发银行,10.00,10.10,10.25,10.30,9.90,10.24,10.25,100,1000,'
+        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";\n'
+        'var hq_str_sz000001="平安银行,12.00,12.10,12.25,12.30,11.90,12.24,12.25,100,1000,'
+        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";'
+    ).encode("gbk")
+
+    def 读取行情(url: str) -> bytes:
+        requested_urls.append(url)
+        return response
+
+    collected_at = datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC)
+
+    quotes = SinaHttpAdapter(读取行情).fetch_quotes(["sh600000", "sz000001"], collected_at)
+
+    assert requested_urls == ["http://hq.sinajs.cn/list=sh600000,sz000001"]
+    assert [quote.price for quote in quotes] == [10.25, 12.25]
+    assert [quote.security_id.display_code for quote in quotes] == ["600000", "000001"]
+    assert [quote.security_id.exchange for quote in quotes] == ["SSE", "SZSE"]
+    assert all(quote.security_id.market is Market.CN for quote in quotes)
+    assert all(quote.source_id == "sina" for quote in quotes)
+    assert all(quote.market_time.tzinfo is not None for quote in quotes)
+    assert all(quote.market_time.tzinfo.key == "Asia/Shanghai" for quote in quotes)
+    assert all(quote.data_version.startswith("sina-") for quote in quotes)
+    assert all(quote.freshness.state == "REALTIME" for quote in quotes)
+    assert all(quote.freshness.age_seconds == 3 for quote in quotes)
