"""验证数据源凭据配置只保存引用且支持重新授权。"""

import pytest


def test_凭据配置拒绝空数据源和空密钥() -> None:
    """无效配置不能创建安全存储引用或启动数据读取。"""

    from stock_agent.application.data_source_credential_service import CredentialRegistration

    with pytest.raises(ValueError):
        CredentialRegistration(source_id="", secret="valid-secret")
    with pytest.raises(ValueError):
        CredentialRegistration(source_id="licensed-source", secret="")


def test_授权记录只暴露引用不暴露明文凭据() -> None:
    """界面和 MCP 只能看到数据源状态与安全存储引用。"""

    from stock_agent.application.data_source_credential_service import CredentialAuthorization

    authorization = CredentialAuthorization(
        source_id="licensed-source", credential_reference="platform-keychain://licensed-source/1"
    )

    assert authorization.credential_reference.startswith("platform-keychain://")
    assert not hasattr(authorization, "secret")


def test_配置撤销与受限桌面状态不暴露凭据(tmp_path) -> None:
    """同一数据目录只能由一个进程持锁，撤销授权后界面必须明确降级。"""

    from stock_agent.adapters.platform.credential_store import ReferenceCredentialStore
    from stock_agent.adapters.platform.paths import RuntimeLock, RuntimeLockError
    from stock_agent.application.data_source_credential_service import (
        CredentialRegistration,
        DataSourceCredentialService,
    )
    from stock_agent.desktop.pages.data_source_page import DataSourcePageState

    first_lock = RuntimeLock(tmp_path)
    first_lock.acquire()
    try:
        with pytest.raises(RuntimeLockError):
            RuntimeLock(tmp_path).acquire()

        service = DataSourceCredentialService(ReferenceCredentialStore())
        authorization = service.configure(
            CredentialRegistration("licensed-source", "never-log-this")
        )
        configured = DataSourcePageState.from_authorization(authorization)
        assert configured.access_state == "已授权"
        assert "never-log-this" not in configured.summary

        service.revoke("licensed-source")
        restricted = DataSourcePageState.from_authorization(service.status("licensed-source"))
        assert restricted.access_state == "受限"
        assert restricted.summary == "未配置可用凭据，相关数据源已降级。"
    finally:
        first_lock.release()


def test_系统凭据保险库只向业务层返回引用() -> None:
    """正式适配器必须把明文停留在系统钥匙串，而非应用内存或配置文件。"""

    from stock_agent.adapters.platform.credential_store import KeyringCredentialStore

    class FakeKeyring:
        def __init__(self) -> None:
            self.items: dict[tuple[str, str], str] = {}

        def set_password(self, service_name: str, username: str, password: str) -> None:
            self.items[(service_name, username)] = password

        def delete_password(self, service_name: str, username: str) -> None:
            self.items.pop((service_name, username))

    fake_keyring = FakeKeyring()
    store = KeyringCredentialStore(keyring_backend=fake_keyring)
    reference = store.put("licensed-source", "never-log-this")
    store.delete(reference)

    assert reference.startswith("platform-keychain://licensed-source/")
    assert fake_keyring.items == {}


def test_新浪为公开只读候选且明确不保证实时() -> None:
    """新浪只能作为无需凭据的 A 股公开只读候选，不能承诺实时行情。"""

    from stock_agent.adapters.platform.credential_store import ReferenceCredentialStore
    from stock_agent.application.data_source_credential_service import (
        DataSourceCredentialService,
    )

    selection = DataSourceCredentialService(ReferenceCredentialStore()).selection_record("sina")

    assert selection.source_id == "sina"
    assert selection.supported_markets == ("CN",)
    assert selection.requires_credentials is False
    assert selection.access_state == "公开只读"
    assert "不保证实时" in selection.degradation_notice
    assert "URL" in selection.audit_note
    assert "市场时间" in selection.audit_note
    assert "新鲜度" in selection.audit_note


def test_finnhub未授权时受限配置后授权且页面不泄露凭据或引用() -> None:
    """Finnhub 仅在系统钥匙串保存用户自带密钥，页面始终不展示密钥或引用。"""

    from stock_agent.adapters.platform.credential_store import ReferenceCredentialStore
    from stock_agent.application.data_source_credential_service import (
        CredentialRegistration,
        DataSourceCredentialService,
    )
    from stock_agent.desktop.pages.data_source_page import DataSourcePageState

    service = DataSourceCredentialService(ReferenceCredentialStore())
    restricted = service.selection_record("finnhub")
    assert restricted.supported_markets == ("US",)
    assert restricted.requires_credentials is True
    assert restricted.access_state == "受限"
    assert "无密钥降级" in restricted.degradation_notice

    service.configure(CredentialRegistration("finnhub", "test-secret"))
    configured = DataSourcePageState.from_selection_record(service.selection_record("finnhub"))
    assert configured.access_state == "已授权"
    assert "test-secret" not in configured.summary
    assert "platform-keychain://" not in configured.summary

    service.revoke("finnhub")
    revoked = service.selection_record("finnhub")
    assert revoked.access_state == "受限"
    assert "不混用" in revoked.audit_note
    assert "不绕过许可" in revoked.audit_note
