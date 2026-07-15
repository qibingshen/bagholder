# Task 4 最终复审包

## 提交

4368ebb fix: clear stale finnhub authorization
e103cfd fix: restrict market source credential state
1ab6b5a feat: configure sina and finnhub market sources

## 统计

 .superpowers/sdd/task-4-report.md                  |  92 +++++++++++++
 docs/acceptance/data-source-selection.md           |  23 ++++
 .../application/data_source_credential_service.py  | 150 +++++++++++++++++++++
 src/stock_agent/desktop/pages/data_source_page.py  |  24 ++++
 tests/contract/test_data_source_credentials.py     | 149 ++++++++++++++++++++
 5 files changed, 438 insertions(+)

## 差异

```diff
diff --git a/.superpowers/sdd/task-4-report.md b/.superpowers/sdd/task-4-report.md
new file mode 100644
index 0000000..195f630
--- /dev/null
+++ b/.superpowers/sdd/task-4-report.md
@@ -0,0 +1,92 @@
+# Task 4：新浪与 Finnhub 配置及选择证据报告
+
+## 完成文件
+
+- `src/stock_agent/application/data_source_credential_service.py`
+- `src/stock_agent/desktop/pages/data_source_page.py`
+- `tests/contract/test_data_source_credentials.py`
+- `docs/acceptance/data-source-selection.md`
+
+## 实现摘要
+
+- 增加不可变数据源元数据：新浪仅支持 `CN`、公开只读且不保证实时；Finnhub 仅支持 `US`、需要凭据且未授权时受限。
+- 增加不含明文密钥和钥匙串引用的选择记录，包含市场、凭据需求、访问状态、降级说明和审计说明。
+- Finnhub 配置后显示“已授权”，撤销后恢复“受限”；新浪拒绝凭据配置。
+- 页面新增从脱敏选择记录生成摘要的入口，不展示明文密钥或钥匙串引用。
+- 补充验收文档，明确 URL 能力、市场时间与新鲜度限制、合法密钥、无密钥降级、不混用和不绕过许可。
+
+## TDD 证据
+
+先在 `tests/contract/test_data_source_credentials.py` 添加新浪元数据与 Finnhub 授权生命周期测试，再运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py -v
+```
+
+失败结果：新增两个测试均因 `DataSourceCredentialService` 缺少 `selection_record` 报 `AttributeError`；原有四个测试通过。随后完成最小实现。
+
+## 验证命令与结果
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+```
+
+结果：8 个测试全部通过；Ruff 格式检查通过（55 个文件已格式化）；Ruff 静态检查通过。
+
+## 自检
+
+- 选择记录和页面摘要均不从 `CredentialAuthorization.credential_reference` 取值。
+- 本任务未新增 Finnhub HTTP、网络、券商、交易、下单或自动交易实现。
+- 仅修改任务要求的 4 个业务、测试和文档文件，并新增本报告。
+
+## Concerns
+
+- 当前桌面层仅提供页面状态模型；实际 PySide6 视图尚未在本任务范围内，因此调用方需要使用 `from_selection_record` 渲染选择摘要。
+
+## 修复与复验
+
+审查修复后，公开的 `CredentialAuthorization` 仅包含 `source_id` 和 `is_authorized`；钥匙串引用仅存于服务内部私有映射。配置仅允许 Finnhub 且要求 `KeyringCredentialStore`，新浪、未知源和非钥匙串存储均明确失败。撤销仅允许 Finnhub，查询和选择记录仅允许受控数据源。页面移除了 `from_authorization`，只接收脱敏的选择记录，因此新浪会保留“公开只读”状态。
+
+本次先替换契约测试并执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py -v
+```
+
+红灯结果：5 项中 4 项失败，分别证明公开对象仍暴露钥匙串引用、Finnhub 配置引用泄露、未知源可配置，以及页面仍存在 `from_authorization`；新浪选择记录测试通过。
+
+最小修复后执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+复验结果：7 项测试全部通过；Ruff 格式检查通过（55 个文件已格式化）；Ruff 静态检查通过；差异检查通过。
+
+## 修复与复验（二）
+
+重配 Finnhub 时，服务现在先从私有引用映射移除旧引用，再删除旧钥匙串项并写入新密钥。新密钥写入失败时不会遗留陈旧引用，因此公开 `status()` 返回未授权，选择记录返回“受限”；公开对象和选择记录仍不包含密钥或钥匙串引用。
+
+先添加失败场景测试并执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py -v
+```
+
+红灯结果：新增“Finnhub 重配写入失败后公开状态恢复受限且不泄露引用”测试失败，实际 `is_authorized` 为 `True`，证明旧私有引用仍导致伪授权。
+
+最小修复并格式化后执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py -v
+py -3.12 -m ruff format --check src tests
+py -3.12 -m ruff check src tests
+git diff --check
+```
+
+复验结果：8 项测试全部通过；Ruff 格式检查通过（55 个文件已格式化）；Ruff 静态检查通过；差异检查通过。
diff --git a/docs/acceptance/data-source-selection.md b/docs/acceptance/data-source-selection.md
new file mode 100644
index 0000000..65e5e31
--- /dev/null
+++ b/docs/acceptance/data-source-selection.md
@@ -0,0 +1,23 @@
+# 数据源选择验收说明
+
+## 配置边界
+
+| 数据源 | 市场 | 凭据 | 初始访问状态 | 降级说明 |
+| --- | --- | --- | --- | --- |
+| 新浪 | `CN` | 不需要 | 公开只读 | 新浪 URL 仅作为公开只读 A 股候选能力，受市场时间和数据新鲜度限制，不保证实时。 |
+| Finnhub | `US` | 需要 | 受限 | 用户未配置合法密钥时，保持受限，不提供美股实时数据。 |
+
+新浪不接受凭据配置。Finnhub 的用户自带合法密钥仅通过 `KeyringCredentialStore` 写入系统钥匙串；服务内部私有记录可撤销引用，公开状态、页面摘要和审计选择记录均不写入明文密钥或钥匙串引用。
+
+## 选择记录
+
+选择记录固定包含数据源标识、支持市场、是否需要凭据、访问状态、降级说明和审计说明。新浪记录说明 URL 能力及市场时间、新鲜度限制；Finnhub 记录说明用户自带合法密钥、无密钥降级、数据源不混用且不绕过许可。
+
+## 验收步骤
+
+1. 查询新浪选择记录，确认市场为 `CN`、状态为“公开只读”，并包含“不保证实时”。
+2. 未配置 Finnhub 密钥时查询选择记录，确认市场为 `US`、状态为“受限”。
+3. 通过系统钥匙串配置 Finnhub 密钥后，确认状态变为“已授权”；页面中不得出现密钥或 `platform-keychain://`。
+4. 撤销 Finnhub 授权后，确认状态恢复为“受限”。
+
+本任务不实现 Finnhub HTTP 调用、真实网络访问、券商或任何交易、下单和自动交易能力。
diff --git a/src/stock_agent/application/data_source_credential_service.py b/src/stock_agent/application/data_source_credential_service.py
new file mode 100644
index 0000000..c5bb6bb
--- /dev/null
+++ b/src/stock_agent/application/data_source_credential_service.py
@@ -0,0 +1,150 @@
+"""管理受控数据源授权，确保公开状态、审计和页面不携带密钥或钥匙串引用。"""
+
+from dataclasses import dataclass
+from types import MappingProxyType
+
+from stock_agent.adapters.platform.credential_store import (
+    CredentialStore,
+    KeyringCredentialStore,
+)
+
+
+@dataclass(frozen=True, slots=True)
+class CredentialRegistration:
+    """接收短生命周期的密钥输入，仅允许由 Finnhub 配置路径消费。"""
+
+    source_id: str
+    secret: str
+
+    def __post_init__(self) -> None:
+        if not self.source_id.strip() or not self.secret:
+            raise ValueError("数据源与凭据不能为空")
+
+
+@dataclass(frozen=True, slots=True)
+class CredentialAuthorization:
+    """面向普通调用方的脱敏授权状态，不包含密钥或钥匙串引用。"""
+
+    source_id: str
+    is_authorized: bool
+
+
+@dataclass(frozen=True, slots=True)
+class DataSourceMetadata:
+    """不可变的数据源配置，仅描述市场范围、授权边界和降级规则。"""
+
+    source_id: str
+    supported_markets: tuple[str, ...]
+    requires_credentials: bool
+    access_state: str
+    degradation_notice: str
+
+
+@dataclass(frozen=True, slots=True)
+class DataSourceSelectionRecord:
+    """可复核的数据源选择记录，不包含明文密钥或钥匙串引用。"""
+
+    source_id: str
+    supported_markets: tuple[str, ...]
+    requires_credentials: bool
+    access_state: str
+    degradation_notice: str
+    audit_note: str
+
+
+DATA_SOURCE_METADATA = MappingProxyType(
+    {
+        "sina": DataSourceMetadata(
+            source_id="sina",
+            supported_markets=("CN",),
+            requires_credentials=False,
+            access_state="公开只读",
+            degradation_notice="公开只读且不保证实时；仅作为 A 股候选数据源。",
+        ),
+        "finnhub": DataSourceMetadata(
+            source_id="finnhub",
+            supported_markets=("US",),
+            requires_credentials=True,
+            access_state="受限",
+            degradation_notice="无密钥降级为受限状态，不提供美股实时数据。",
+        ),
+    }
+)
+
+_SELECTION_AUDIT_NOTES = MappingProxyType(
+    {
+        "sina": "新浪 URL 仅支持公开只读能力；受市场时间与数据新鲜度限制，不保证实时。",
+        "finnhub": "Finnhub 由用户自带合法密钥；无密钥降级，数据源不混用且不绕过许可。",
+    }
+)
+
+
+class DataSourceCredentialService:
+    """协调受控数据源与系统钥匙串，公开接口只返回脱敏状态。"""
+
+    def __init__(self, credential_store: CredentialStore) -> None:
+        self._credential_store = credential_store
+        self._credential_references: dict[str, str] = {}
+
+    def configure(self, registration: CredentialRegistration) -> CredentialAuthorization:
+        """仅通过系统钥匙串配置 Finnhub，并返回不含引用的授权状态。"""
+
+        self._require_finnhub_credential_operation(registration.source_id)
+        if not isinstance(self._credential_store, KeyringCredentialStore):
+            raise ValueError("Finnhub 凭据必须使用系统钥匙串存储")
+
+        previous_reference = self._credential_references.pop(registration.source_id, None)
+        if previous_reference is not None:
+            self._credential_store.delete(previous_reference)
+        self._credential_references[registration.source_id] = self._credential_store.put(
+            registration.source_id, registration.secret
+        )
+        return CredentialAuthorization(registration.source_id, is_authorized=True)
+
+    def revoke(self, source_id: str) -> CredentialAuthorization:
+        """仅撤销 Finnhub 的内部钥匙串引用并返回脱敏受限状态。"""
+
+        self._require_finnhub_credential_operation(source_id)
+        previous_reference = self._credential_references.pop(source_id, None)
+        if previous_reference is not None:
+            self._credential_store.delete(previous_reference)
+        return CredentialAuthorization(source_id, is_authorized=False)
+
+    def status(self, source_id: str) -> CredentialAuthorization:
+        """查询受控数据源的脱敏状态；未知数据源明确失败。"""
+
+        metadata = self._metadata_for(source_id)
+        if not metadata.requires_credentials:
+            return CredentialAuthorization(source_id, is_authorized=True)
+        return CredentialAuthorization(
+            source_id, is_authorized=source_id in self._credential_references
+        )
+
+    def selection_record(self, source_id: str) -> DataSourceSelectionRecord:
+        """返回可审计的选择状态，永不携带凭据或钥匙串引用。"""
+
+        metadata = self._metadata_for(source_id)
+        access_state = metadata.access_state
+        if metadata.requires_credentials and self.status(source_id).is_authorized:
+            access_state = "已授权"
+
+        return DataSourceSelectionRecord(
+            source_id=metadata.source_id,
+            supported_markets=metadata.supported_markets,
+            requires_credentials=metadata.requires_credentials,
+            access_state=access_state,
+            degradation_notice=metadata.degradation_notice,
+            audit_note=_SELECTION_AUDIT_NOTES[source_id],
+        )
+
+    @staticmethod
+    def _metadata_for(source_id: str) -> DataSourceMetadata:
+        metadata = DATA_SOURCE_METADATA.get(source_id)
+        if metadata is None:
+            raise ValueError("不支持的数据源")
+        return metadata
+
+    def _require_finnhub_credential_operation(self, source_id: str) -> None:
+        self._metadata_for(source_id)
+        if source_id != "finnhub":
+            raise ValueError("仅 Finnhub 支持凭据操作")
diff --git a/src/stock_agent/desktop/pages/data_source_page.py b/src/stock_agent/desktop/pages/data_source_page.py
new file mode 100644
index 0000000..997f7be
--- /dev/null
+++ b/src/stock_agent/desktop/pages/data_source_page.py
@@ -0,0 +1,24 @@
+"""定义数据源选择页面的安全状态模型。"""
+
+from dataclasses import dataclass
+
+from stock_agent.application.data_source_credential_service import DataSourceSelectionRecord
+
+
+@dataclass(frozen=True, slots=True)
+class DataSourcePageState:
+    """桌面端只从脱敏选择记录渲染数据源状态与摘要。"""
+
+    source_id: str
+    access_state: str
+    summary: str
+
+    @classmethod
+    def from_selection_record(cls, selection: DataSourceSelectionRecord) -> "DataSourcePageState":
+        """将不含敏感字段的选择记录转换为桌面摘要。"""
+
+        return cls(
+            source_id=selection.source_id,
+            access_state=selection.access_state,
+            summary=f"{selection.degradation_notice} {selection.audit_note}",
+        )
diff --git a/tests/contract/test_data_source_credentials.py b/tests/contract/test_data_source_credentials.py
new file mode 100644
index 0000000..24f39eb
--- /dev/null
+++ b/tests/contract/test_data_source_credentials.py
@@ -0,0 +1,149 @@
+"""验证新浪和 Finnhub 的受控配置、公开状态与页面脱敏边界。"""
+
+import pytest
+
+
+class FakeKeyring:
+    """记录系统钥匙串调用，供受控配置路径验收使用。"""
+
+    def __init__(self) -> None:
+        self.items: dict[tuple[str, str], str] = {}
+        self.fail_next_write = False
+
+    def set_password(self, service_name: str, username: str, password: str) -> None:
+        if self.fail_next_write:
+            self.fail_next_write = False
+            raise RuntimeError("系统钥匙串写入失败")
+        self.items[(service_name, username)] = password
+
+    def delete_password(self, service_name: str, username: str) -> None:
+        self.items.pop((service_name, username))
+
+
+def test_公开授权状态不含密钥或钥匙串引用() -> None:
+    """普通调用方只能得到脱敏授权状态，不能读取内部钥匙串引用。"""
+
+    from stock_agent.application.data_source_credential_service import CredentialAuthorization
+
+    authorization = CredentialAuthorization(source_id="finnhub", is_authorized=True)
+
+    assert authorization.is_authorized is True
+    assert not hasattr(authorization, "secret")
+    assert not hasattr(authorization, "credential_reference")
+    assert "platform-keychain://" not in str(authorization)
+
+
+def test_新浪为公开只读候选且页面保持公开状态() -> None:
+    """新浪只能作为无需凭据的 A 股公开只读候选，不能承诺实时行情。"""
+
+    from stock_agent.adapters.platform.credential_store import ReferenceCredentialStore
+    from stock_agent.application.data_source_credential_service import (
+        DataSourceCredentialService,
+    )
+    from stock_agent.desktop.pages.data_source_page import DataSourcePageState
+
+    selection = DataSourceCredentialService(ReferenceCredentialStore()).selection_record("sina")
+    page_state = DataSourcePageState.from_selection_record(selection)
+
+    assert selection.source_id == "sina"
+    assert selection.supported_markets == ("CN",)
+    assert selection.requires_credentials is False
+    assert selection.access_state == "公开只读"
+    assert "不保证实时" in selection.degradation_notice
+    assert page_state.access_state == "公开只读"
+    assert "URL" in selection.audit_note
+    assert "市场时间" in selection.audit_note
+    assert "新鲜度" in selection.audit_note
+
+
+def test_finnhub仅通过系统钥匙串配置并在撤销后恢复受限() -> None:
+    """Finnhub 密钥必须进入 KeyringCredentialStore，公开状态和页面均不泄露引用。"""
+
+    from stock_agent.adapters.platform.credential_store import KeyringCredentialStore
+    from stock_agent.application.data_source_credential_service import (
+        CredentialRegistration,
+        DataSourceCredentialService,
+    )
+    from stock_agent.desktop.pages.data_source_page import DataSourcePageState
+
+    fake_keyring = FakeKeyring()
+    service = DataSourceCredentialService(KeyringCredentialStore(keyring_backend=fake_keyring))
+    assert service.status("finnhub").is_authorized is False
+    assert service.selection_record("finnhub").access_state == "受限"
+
+    configured = service.configure(CredentialRegistration("finnhub", "test-secret"))
+    page_state = DataSourcePageState.from_selection_record(service.selection_record("finnhub"))
+    assert configured.is_authorized is True
+    assert len(fake_keyring.items) == 1
+    assert page_state.access_state == "已授权"
+    assert "test-secret" not in page_state.summary
+    assert "platform-keychain://" not in page_state.summary
+    assert "platform-keychain://" not in str(configured)
+
+    revoked = service.revoke("finnhub")
+    assert revoked.is_authorized is False
+    assert fake_keyring.items == {}
+    assert service.selection_record("finnhub").access_state == "受限"
+
+
+def test_finnhub重配写入失败后公开状态恢复受限且不泄露引用() -> None:
+    """重配失败不能保留已删除凭据的陈旧引用或继续显示已授权。"""
+
+    from stock_agent.adapters.platform.credential_store import KeyringCredentialStore
+    from stock_agent.application.data_source_credential_service import (
+        CredentialRegistration,
+        DataSourceCredentialService,
+    )
+
+    fake_keyring = FakeKeyring()
+    service = DataSourceCredentialService(KeyringCredentialStore(keyring_backend=fake_keyring))
+    service.configure(CredentialRegistration("finnhub", "first-secret"))
+
+    fake_keyring.fail_next_write = True
+    with pytest.raises(RuntimeError, match="系统钥匙串写入失败"):
+        service.configure(CredentialRegistration("finnhub", "second-secret"))
+
+    authorization = service.status("finnhub")
+    selection = service.selection_record("finnhub")
+    assert authorization.is_authorized is False
+    assert selection.access_state == "受限"
+    assert fake_keyring.items == {}
+    assert "first-secret" not in str(authorization)
+    assert "second-secret" not in str(selection)
+    assert "platform-keychain://" not in str(authorization)
+    assert "platform-keychain://" not in str(selection)
+
+
+def test_凭据操作拒绝非finnhub和非钥匙串存储() -> None:
+    """新浪、未知源及非系统钥匙串都不能创建、删除或伪造授权状态。"""
+
+    from stock_agent.adapters.platform.credential_store import ReferenceCredentialStore
+    from stock_agent.application.data_source_credential_service import (
+        CredentialRegistration,
+        DataSourceCredentialService,
+    )
+
+    service = DataSourceCredentialService(ReferenceCredentialStore())
+
+    with pytest.raises(ValueError):
+        service.configure(CredentialRegistration("sina", "test-secret"))
+    with pytest.raises(ValueError):
+        service.configure(CredentialRegistration("unknown", "test-secret"))
+    with pytest.raises(ValueError):
+        service.configure(CredentialRegistration("finnhub", "test-secret"))
+    with pytest.raises(ValueError):
+        service.revoke("sina")
+    with pytest.raises(ValueError):
+        service.revoke("unknown")
+    with pytest.raises(ValueError):
+        service.status("unknown")
+    with pytest.raises(ValueError):
+        service.selection_record("unknown")
+
+
+def test_页面只接受脱敏选择记录() -> None:
+    """页面不能从授权对象推断状态，避免密钥引用进入渲染路径。"""
+
+    from stock_agent.desktop.pages.data_source_page import DataSourcePageState
+
+    assert not hasattr(DataSourcePageState, "from_authorization")

```

