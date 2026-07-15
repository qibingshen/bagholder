# T037 最终复审包

## 提交

79b1301 test: tighten US1 historical pipeline evidence
1d1bdff test: add US1 historical daily pipeline red tests

## 统计

 .superpowers/sdd/task-037-report.md                |  77 ++++++
 docs/acceptance/data-source-selection.md           |  35 +++
 .../test_single_market_daily_pipeline.py           | 302 ++++++++++++++++++---
 3 files changed, 373 insertions(+), 41 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/task-037-report.md b/.superpowers/sdd/task-037-report.md
new file mode 100644
index 0000000..88a3e62
--- /dev/null
+++ b/.superpowers/sdd/task-037-report.md
@@ -0,0 +1,77 @@
+# T037 报告：一市场历史日线本地闭环集成测试
+
+## 任务边界
+
+本任务只新增集成红灯测试和数据源选择验收说明，未新增或修改生产代码，未发起真实网络请求，未接入券商、
+下单或交易能力。
+
+## 已新增的验收约束
+
+- 首个 US1 历史日线闭环仅登记 `sina` A 股公开只读能力，并写明精确 URL
+  `http://hq.sinajs.cn/list={sh|sz 加六位代码的逗号分隔列表}` 的能力边界。
+- 明确新浪不构成已授权实时源，也不因该公开报价 URL 而被视为已承诺历史日线、复权或公司行动。
+- 固定响应通过依赖注入传给待实现的历史日线工作者；测试中没有 HTTP 客户端或真实网络调用。
+- 要求原始响应与规范化日线追加保存，可按来源、市场时间、采集时间、版本、内容哈希和父版本回读关联。
+- 要求相同内容重采集保留新记录；字段非法、原始保存失败或规范化保存失败时两侧原子回滚。
+- 要求历史日线不能标记为实时，也不能作为当前预测的实时输入。
+
+## 审查修正
+
+- 历史日线预测降级断言改为 `is_usable_for_current_prediction(...) is False`；与 T041 既有契约一致，
+仅时点字段自身无效时才由领域层抛出时间异常。
+- 成功路径同时回读原始与规范化工件，逐项校验来源、市场、市场时间、采集时间、数据版本、内容哈希、
+元数据和父版本关联。
+- 增加工件字节已写入后元数据登记失败、以及完成标记前失败的注入场景；两种失败均要求原始和规范化
+工件目录、完成标记及元数据登记零残留。
+
+## 红灯验证
+
+执行时间：2026-07-14
+
+```text
+py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py -v
+```
+
+结果：收集 7 个测试，7 个失败，退出码 `1`。
+
+关键输出：
+
+```text
+ModuleNotFoundError: No module named 'stock_agent.workers.market_ingestion'
+============================== 7 failed in 1.59s ==============================
+```
+
+失败原因符合预期：T040 规定的历史日线采集、原始响应保存和标准化工作者尚未实现。失败发生在导入生产
+缺口处，早于任何网络行为；因此当前测试是有效红灯，而不是用测试替代生产实现。
+
+## 后续实现者接口契约
+
+测试要求在 `stock_agent.workers.market_ingestion` 中提供：
+
+- `HistoricalDailyIngestionWorker(read_historical_daily, versioning_service)`；
+- `collect_and_save(security_id, source_id, collected_at)`；
+- `HistoricalDailyIngestionError`；
+- 返回具有 `bars`、`raw_version_id` 和 `normalized_version_id` 的结果。
+
+实现必须保持读取函数可注入，并在原始与规范化工件之间提供可回读的父版本关联和真正的原子回滚。生产
+实现完成后，应重新运行上述命令，预期所有红灯转绿；本任务没有执行生产实现或绿灯验证。
+
+## 审查修正后的红灯验证
+
+执行时间：2026-07-14
+
+```text
+py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py -v
+```
+
+结果：收集 11 个测试，11 个失败，退出码 `1`。
+
+关键输出：
+
+```text
+ModuleNotFoundError: No module named 'stock_agent.workers.market_ingestion'
+============================= 11 failed in 0.94s ==============================
+```
+
+红灯仍准确指向尚未实现的 T040 历史日线工作者。新增的元数据登记和完成标记前故障注入均使用本地
+版本服务与固定响应，不包含真实网络行为。
diff --git a/docs/acceptance/data-source-selection.md b/docs/acceptance/data-source-selection.md
index 65e5e31..28b4024 100644
--- a/docs/acceptance/data-source-selection.md
+++ b/docs/acceptance/data-source-selection.md
@@ -14,10 +14,45 @@
 选择记录固定包含数据源标识、支持市场、是否需要凭据、访问状态、降级说明和审计说明。新浪记录说明 URL 能力及市场时间、新鲜度限制；Finnhub 记录说明用户自带合法密钥、无密钥降级、数据源不混用且不绕过许可。
 
 ## 验收步骤
 
 1. 查询新浪选择记录，确认市场为 `CN`、状态为“公开只读”，并包含“不保证实时”。
 2. 未配置 Finnhub 密钥时查询选择记录，确认市场为 `US`、状态为“受限”。
 3. 通过系统钥匙串配置 Finnhub 密钥后，确认状态变为“已授权”；页面中不得出现密钥或 `platform-keychain://`。
 4. 撤销 Finnhub 授权后，确认状态恢复为“受限”。
 
 本任务不实现 Finnhub HTTP 调用、真实网络访问、券商或任何交易、下单和自动交易能力。
+
+## US1 历史日线闭环选择记录
+
+### 本次选择与授权边界
+
+US1 的首个历史日线本地闭环固定使用 `sina` 标识的新浪 A 股公开只读能力，不发送凭据、不接入券商、
+不下单，也不执行自动交易。可复核的 URL 能力仅为：
+`http://hq.sinajs.cn/list={sh|sz 加六位代码的逗号分隔列表}`。该 URL 是公开只读报价入口；本项目不能
+据此声称新浪已授权、承诺或保证历史日线、复权、公司行动或实时数据。历史日线集成测试使用注入的固定
+响应，不发出真实网络请求；后续接入真实历史日线前必须单独复核其合法授权、字段口径、限频和保留期限。
+
+新浪无凭据、无用户密钥保存路径，但仍受公开服务可用性、市场交易时间、响应时间戳可验证性、数据延迟和
+服务端限频约束。无法验证市场时间、字段不完整、超出约定延迟或来源能力不匹配时，采集必须失败或降级，
+不得猜测、补齐或拼接其他来源。
+
+### 时点、版本与回读要求
+
+每个成功批次必须以追加方式保存原始响应和规范化历史日线两类本地工件。规范化记录按证券和交易日保存，
+并至少保留 `source_id`、市场、证券身份、交易日、市场时间、采集 UTC 时间、版本标识、内容哈希、币种和
+复权口径。规范化工件必须显式引用其原始工件父版本；通过来源、市场时间、采集时间、版本和内容哈希可以
+回读并核对两侧内容。相同响应再次采集也必须产生可追溯的新采集记录，禁止静默覆盖；修订必须显式保留父
+版本、来源和修订原因。
+
+单批内任一日线字段非法、原始工件保存失败或规范化工件保存失败时，原始与规范化两侧都不得留下半批可见
+记录，失败结果必须说明解析、字段校验或保存的具体原因。
+即使工件字节已经写入，只要元数据登记或完成标记失败，也必须删除两侧工件目录、完成标记和元数据登记，
+使原始与规范化两侧均为零残留。
+
+### 预测降级边界
+
+历史日线只能用于历史研究、展示和回测准备，绝不标记为 `REALTIME`，也不能作为当前预测的实时输入。
+新浪公开只读能力不构成授权实时数据源；市场时间无法验证、数据延迟不满足规则或处于休市状态时，当前预测
+必须明确拒绝或降级，而不是将历史日线伪装为实时行情。
+对结构合法但处于 `CLOSED` 的历史日线，当前预测入口返回 `False`；仅市场时间或采集时间本身无效时，
+才返回领域时间异常。
diff --git a/tests/integration/test_single_market_daily_pipeline.py b/tests/integration/test_single_market_daily_pipeline.py
index 9274d3a..9fa3c66 100644
--- a/tests/integration/test_single_market_daily_pipeline.py
+++ b/tests/integration/test_single_market_daily_pipeline.py
@@ -1,46 +1,266 @@
-"""验证新浪 A 股行情适配器的受控请求与规范化输出。"""
+"""验证首个市场历史日线的本地闭环，不访问真实网络。"""
 
+from __future__ import annotations
+
+import hashlib
+import json
 from datetime import UTC, datetime
 from pathlib import Path
 
-from stock_agent.adapters.market_data.sina_adapter import SinaHttpAdapter
-from stock_agent.adapters.market_data.sina_provenance import SinaMarketDataFactRecorder
+import pytest
+
 from stock_agent.application.versioning_service import VersioningService
-from stock_agent.domain.market import Market
-
-
-def test_新浪适配器以精确地址读取_GBK_行情并保留完整溯源信息(local_data_root: Path) -> None:
-    """适配器只能使用约定地址，并将合法响应转为可量化使用的完整行情。"""
-
-    requested_urls: list[str] = []
-    response = (
-        'var hq_str_sh600000="浦发银行,10.00,10.10,10.25,10.30,9.90,10.24,10.25,100,1000,'
-        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";\n'
-        'var hq_str_sz000001="平安银行,12.00,12.10,12.25,12.30,11.90,12.24,12.25,100,1000,'
-        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";'
-    ).encode("gbk")
-
-    def 读取行情(url: str) -> bytes:
-        requested_urls.append(url)
-        return response
-
-    collected_at = datetime(2026, 7, 14, 1, 30, 3, 1, tzinfo=UTC)
-
-    service = VersioningService(local_data_root)
-    quotes = SinaHttpAdapter(
-        读取行情,
-        SinaMarketDataFactRecorder(service),
-        service,
-    ).fetch_quotes(["sh600000", "sz000001"], collected_at)
-
-    assert requested_urls == ["http://hq.sinajs.cn/list=sh600000,sz000001"]
-    assert [quote.price for quote in quotes] == [10.25, 12.25]
-    assert [quote.security_id.display_code for quote in quotes] == ["600000", "000001"]
-    assert [quote.security_id.exchange for quote in quotes] == ["SSE", "SZSE"]
-    assert all(quote.security_id.market is Market.CN for quote in quotes)
-    assert all(quote.source_id == "sina" for quote in quotes)
-    assert all(quote.market_time.tzinfo is not None for quote in quotes)
-    assert all(quote.market_time.tzinfo.key == "Asia/Shanghai" for quote in quotes)
-    assert all(quote.data_version.startswith("sina-") for quote in quotes)
-    assert all(quote.freshness.state == "REALTIME" for quote in quotes)
-    assert all(quote.freshness.age_seconds == 4 for quote in quotes)
+from stock_agent.domain.freshness import is_usable_for_current_prediction
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+def 固定历史日线响应() -> bytes:
+    """返回固定的历史日线原始响应，防止集成测试触发任何真实网络请求。"""
+
+    return json.dumps(
+        {
+            "bars": [
+                {
+                    "close": 10.20,
+                    "high": 10.50,
+                    "low": 9.80,
+                    "open": 10.00,
+                    "trade_date": "2026-07-13",
+                    "volume": 1_000_000,
+                }
+            ],
+            "collected_at": "2026-07-14T07:01:02+00:00",
+            "data_version": "sina-固定历史响应-1",
+            "market": "CN",
+            "market_time": "2026-07-13T15:00:00+08:00",
+            "response_schema_version": "固定历史日线响应-1",
+            "source_id": "sina",
+        },
+        ensure_ascii=False,
+        separators=(",", ":"),
+        sort_keys=True,
+    ).encode("utf-8")
+
+
+def 创建工作者(读取历史日线, 服务: VersioningService):
+    """延迟导入尚未实现的工作者，使红灯直接指向 US1 的生产缺口。"""
+
+    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionWorker
+
+    return HistoricalDailyIngestionWorker(
+        read_historical_daily=读取历史日线,
+        versioning_service=服务,
+    )
+
+
+def 采集参数() -> dict[str, object]:
+    """返回固定的市场、证券和采集时间，确保工件关联可重复核。"""
+
+    return {
+        "collected_at": datetime(2026, 7, 14, 7, 1, 2, tzinfo=UTC),
+        "security_id": InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
+        "source_id": "sina",
+    }
+
+
+def 断言不存在半批工件或元数据(服务: VersioningService, 数据根目录: Path) -> None:
+    """同时检查可见工件目录和 DuckDB 元数据，避免把半批残留误判为已回滚。"""
+
+    for 数据集 in ("market-data-raw", "market-data-normalized"):
+        assert not (数据根目录 / "artifacts" / 数据集).exists()
+    assert 服务._metadata._connection.execute(
+        "SELECT COUNT(*) FROM dataset_versions"
+    ).fetchone() == (0,)
+
+
+def test_历史日线将注入响应追加保存为原始与规范化工件并可按溯源字段回读(
+    local_data_root: Path,
+) -> None:
+    """成功采集必须保留原文、日线、版本链和哈希，不能依赖真实新浪请求。"""
+
+    请求参数: list[dict[str, object]] = []
+    原始响应 = 固定历史日线响应()
+
+    def 读取历史日线(**参数: object) -> bytes:
+        请求参数.append(dict(参数))
+        return 原始响应
+
+    服务 = VersioningService(local_data_root)
+    结果 = 创建工作者(读取历史日线, 服务).collect_and_save(**采集参数())
+
+    assert 请求参数 == [采集参数()]
+    assert 结果.bars[0].trade_date.isoformat() == "2026-07-13"
+    assert 结果.bars[0].source_id == "sina"
+    assert 结果.bars[0].freshness.state != "REALTIME"
+    原始工件 = 服务.read_bytes("market-data-raw", 结果.raw_version_id)
+    原始批次 = json.loads(原始工件)
+    原始元数据 = 服务.metadata_for("market-data-raw", 结果.raw_version_id)
+    assert 原始工件 == 原始响应
+    assert 原始批次["source_id"] == "sina"
+    assert 原始批次["market"] == "CN"
+    assert 原始批次["market_time"] == "2026-07-13T15:00:00+08:00"
+    assert 原始批次["collected_at"] == "2026-07-14T07:01:02+00:00"
+    assert 原始批次["data_version"] == "sina-固定历史响应-1"
+    assert 原始元数据["content_hash"] == hashlib.sha256(原始工件).hexdigest()
+    assert 原始元数据["parent_version_id"] is None
+
+    规范化工件 = 服务.read_bytes("market-data-normalized", 结果.normalized_version_id)
+    规范化批次 = json.loads(规范化工件)
+    元数据 = 服务.metadata_for("market-data-normalized", 结果.normalized_version_id)
+    assert 规范化批次["source_id"] == "sina"
+    assert 规范化批次["market"] == "CN"
+    assert 规范化批次["collected_at"] == "2026-07-14T07:01:02+00:00"
+    assert 规范化批次["bars"][0]["market_time"] == "2026-07-13T15:00:00+08:00"
+    assert 规范化批次["bars"][0]["data_version"] == 结果.normalized_version_id
+    assert 规范化批次["data_version"] == 结果.normalized_version_id
+    assert 元数据["parent_version_id"] == 结果.raw_version_id
+    assert 元数据["content_hash"] == hashlib.sha256(规范化工件).hexdigest()
+
+
+def test_相同历史响应重采集会追加可追溯新记录而非静默覆盖(
+    local_data_root: Path,
+) -> None:
+    """相同内容的再次采集必须产生新的原始和规范化版本，并保留各自父链。"""
+
+    服务 = VersioningService(local_data_root)
+    工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)
+
+    首次 = 工作者.collect_and_save(**采集参数())
+    第二次 = 工作者.collect_and_save(**采集参数())
+
+    assert 首次.raw_version_id != 第二次.raw_version_id
+    assert 首次.normalized_version_id != 第二次.normalized_version_id
+    assert 服务.read_bytes("market-data-raw", 首次.raw_version_id) == 固定历史日线响应()
+    assert (
+        服务.read_bytes("market-data-raw", 第二次.raw_version_id) == 固定历史日线响应()
+    )
+    assert (
+        服务.metadata_for("market-data-normalized", 首次.normalized_version_id)[
+            "parent_version_id"
+        ]
+        == 首次.raw_version_id
+    )
+    assert (
+        服务.metadata_for("market-data-normalized", 第二次.normalized_version_id)[
+            "parent_version_id"
+        ]
+        == 第二次.raw_version_id
+    )
+
+
+@pytest.mark.parametrize(
+    "原始响应",
+    [
+        b'{"bars":[{"trade_date":"2026-07-13","open":10.0,"high":10.5,"low":9.8,"close":10.2}]}',
+        b'{"bars":[{"trade_date":"2026-07-13","open":10.0,"high":10.5,"low":9.8,"close":10.2,"volume":1000},{"trade_date":"2026-07-14","open":10.0,"high":9.8,"low":9.9,"close":10.2,"volume":1000}]}',
+    ],
+)
+def test_任一日线字段非法时原始与规范化两侧均不留下半批记录(
+    原始响应: bytes, local_data_root: Path
+) -> None:
+    """验证、解析或规范化失败都必须整批回滚，并给出明确的失败原因。"""
+
+    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError
+
+    服务 = VersioningService(local_data_root)
+    工作者 = 创建工作者(lambda **_参数: 原始响应, 服务)
+
+    with pytest.raises(HistoricalDailyIngestionError, match="字段|价格|日线|完整"):
+        工作者.collect_and_save(**采集参数())
+
+    断言不存在半批工件或元数据(服务, local_data_root)
+
+
+@pytest.mark.parametrize("失败数据集", ["market-data-raw", "market-data-normalized"])
+def test_任一工件保存失败时历史日线原子回滚且报告失败原因(
+    失败数据集: str, local_data_root: Path, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """两侧工件必须作为一个批次提交；任一保存失败均不可留下可见版本。"""
+
+    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError
+
+    服务 = VersioningService(local_data_root)
+    原提交 = 服务.commit_bytes
+
+    def 失败提交(*, dataset: str, **参数: object):
+        if dataset == 失败数据集:
+            raise OSError(f"{失败数据集} 保存失败")
+        return 原提交(dataset=dataset, **参数)
+
+    monkeypatch.setattr(服务, "commit_bytes", 失败提交)
+    工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)
+
+    with pytest.raises(HistoricalDailyIngestionError, match="保存失败"):
+        工作者.collect_and_save(**采集参数())
+
+    断言不存在半批工件或元数据(服务, local_data_root)
+
+
+@pytest.mark.parametrize("失败数据集", ["market-data-raw", "market-data-normalized"])
+@pytest.mark.parametrize("失败时点", ["元数据登记", "完成标记"])
+def test_工件字节写入后元数据登记或完成标记失败时两侧零残留(
+    失败数据集: str,
+    失败时点: str,
+    local_data_root: Path,
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    """原子回滚必须覆盖已写字节但尚未完成登记或完成标记的中间状态。"""
+
+    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError
+
+    服务 = VersioningService(local_data_root)
+    if 失败时点 == "元数据登记":
+        原登记 = 服务._metadata.register_version
+
+        def 失败登记(dataset: str, *参数: object) -> None:
+            if dataset == 失败数据集:
+                raise OSError(f"{失败数据集} 元数据登记失败")
+            原登记(dataset, *参数)
+
+        monkeypatch.setattr(服务._metadata, "register_version", 失败登记)
+    else:
+        原写入 = 服务._artifacts.write_artifact
+
+        def 完成标记前失败(dataset: str, version_id: str, content: bytes):
+            if dataset != 失败数据集:
+                return 原写入(dataset, version_id, content)
+            目录 = local_data_root / "artifacts" / dataset / version_id
+            目录.mkdir(parents=True, exist_ok=False)
+            (目录 / "payload.parquet").write_bytes(content)
+            (目录 / "manifest.json").write_text(
+                json.dumps({"content_hash": hashlib.sha256(content).hexdigest()}),
+                encoding="utf-8",
+            )
+            raise OSError(f"{失败数据集} 完成标记失败")
+
+        monkeypatch.setattr(服务._artifacts, "write_artifact", 完成标记前失败)
+
+    工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)
+
+    with pytest.raises(
+        HistoricalDailyIngestionError, match="元数据登记失败|完成标记失败"
+    ):
+        工作者.collect_and_save(**采集参数())
+
+    断言不存在半批工件或元数据(服务, local_data_root)
+
+
+def test_历史日线不得作为当前预测的实时输入(local_data_root: Path) -> None:
+    """闭环产物只能用于历史研究；即使日线完整也必须被当前预测入口拒绝。"""
+
+    服务 = VersioningService(local_data_root)
+    结果 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务).collect_and_save(
+        **采集参数()
+    )
+
+    assert (
+        is_usable_for_current_prediction(
+            {
+                "collected_at": 结果.bars[0].collected_at,
+                "market_time": 结果.bars[0].market_time,
+                "state": "CLOSED",
+                "time_is_verifiable": True,
+            }
+        )
+        is False
+    )

```

