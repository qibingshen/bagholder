"""验证新浪和 Finnhub 的受控配置、公开状态与页面脱敏边界。"""

import pytest


class FakeKeyring:
    """记录系统钥匙串调用，供受控配置路径验收使用。"""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}
        self.fail_next_write = False
        self.fail_next_delete = False

    def set_password(self, service_name: str, username: str, password: str) -> None:
        if self.fail_next_write:
            self.fail_next_write = False
            raise RuntimeError("系统钥匙串写入失败")
        self.items[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        if self.fail_next_delete:
            self.fail_next_delete = False
            raise RuntimeError("系统钥匙串删除失败")
        self.items.pop((service_name, username))


def test_公开授权状态不含密钥或钥匙串引用() -> None:
    """普通调用方只能得到脱敏授权状态，不能读取内部钥匙串引用。"""

    from stock_agent.application.data_source_credential_service import CredentialAuthorization

    authorization = CredentialAuthorization(source_id="finnhub", is_authorized=True)

    assert authorization.is_authorized is True
    assert not hasattr(authorization, "secret")
    assert not hasattr(authorization, "credential_reference")
    assert "platform-keychain://" not in str(authorization)


def test_新浪为公开只读候选且页面保持公开状态() -> None:
    """新浪只能作为无需凭据的 A 股公开只读候选，不能承诺实时行情。"""

    from stock_agent.adapters.platform.credential_store import ReferenceCredentialStore
    from stock_agent.application.data_source_credential_service import (
        DataSourceCredentialService,
    )
    from stock_agent.desktop.pages.data_source_page import DataSourcePageState

    selection = DataSourceCredentialService(ReferenceCredentialStore()).selection_record("sina")
    page_state = DataSourcePageState.from_selection_record(selection)

    assert selection.source_id == "sina"
    assert selection.supported_markets == ("CN",)
    assert selection.requires_credentials is False
    assert selection.access_state == "公开只读"
    assert "不保证实时" in selection.degradation_notice
    assert page_state.access_state == "公开只读"
    assert "URL" in selection.audit_note
    assert "市场时间" in selection.audit_note
    assert "新鲜度" in selection.audit_note


def test_finnhub仅通过系统钥匙串配置并在撤销后恢复受限() -> None:
    """Finnhub 密钥必须进入 KeyringCredentialStore，公开状态和页面均不泄露引用。"""

    from stock_agent.adapters.platform.credential_store import KeyringCredentialStore
    from stock_agent.application.data_source_credential_service import (
        CredentialRegistration,
        DataSourceCredentialService,
    )
    from stock_agent.desktop.pages.data_source_page import DataSourcePageState

    fake_keyring = FakeKeyring()
    service = DataSourceCredentialService(KeyringCredentialStore(keyring_backend=fake_keyring))
    assert service.status("finnhub").is_authorized is False
    assert service.selection_record("finnhub").access_state == "受限"

    configured = service.configure(CredentialRegistration("finnhub", "test-secret"))
    page_state = DataSourcePageState.from_selection_record(service.selection_record("finnhub"))
    assert configured.is_authorized is True
    assert len(fake_keyring.items) == 1
    assert page_state.access_state == "已授权"
    assert "test-secret" not in page_state.summary
    assert "platform-keychain://" not in page_state.summary
    assert "platform-keychain://" not in str(configured)

    revoked = service.revoke("finnhub")
    assert revoked.is_authorized is False
    assert fake_keyring.items == {}
    assert service.selection_record("finnhub").access_state == "受限"


def test_finnhub重配写入失败后公开状态恢复受限且不泄露引用() -> None:
    """重配失败不能保留已删除凭据的陈旧引用或继续显示已授权。"""

    from stock_agent.adapters.platform.credential_store import KeyringCredentialStore
    from stock_agent.application.data_source_credential_service import (
        CredentialRegistration,
        DataSourceCredentialService,
    )

    fake_keyring = FakeKeyring()
    service = DataSourceCredentialService(KeyringCredentialStore(keyring_backend=fake_keyring))
    service.configure(CredentialRegistration("finnhub", "first-secret"))

    fake_keyring.fail_next_write = True
    with pytest.raises(RuntimeError, match="系统钥匙串写入失败"):
        service.configure(CredentialRegistration("finnhub", "second-secret"))

    authorization = service.status("finnhub")
    selection = service.selection_record("finnhub")
    assert authorization.is_authorized is False
    assert selection.access_state == "受限"
    assert fake_keyring.items == {}
    assert "first-secret" not in str(authorization)
    assert "second-secret" not in str(selection)
    assert "platform-keychain://" not in str(authorization)
    assert "platform-keychain://" not in str(selection)


def test_finnhub撤销删除失败时保留内部重试并公开受限() -> None:
    """删除失败时不能丢失私有引用；重试成功前公开面始终显示受限。"""

    from stock_agent.adapters.platform.credential_store import KeyringCredentialStore
    from stock_agent.application.data_source_credential_service import (
        CredentialRegistration,
        DataSourceCredentialService,
    )

    fake_keyring = FakeKeyring()
    service = DataSourceCredentialService(KeyringCredentialStore(keyring_backend=fake_keyring))
    service.configure(CredentialRegistration("finnhub", "test-secret"))
    fake_keyring.fail_next_delete = True

    with pytest.raises(RuntimeError, match="系统钥匙串删除失败"):
        service.revoke("finnhub")

    assert service.status("finnhub").is_authorized is False
    assert service.selection_record("finnhub").access_state == "受限"
    assert len(fake_keyring.items) == 1
    assert "platform-keychain://" not in str(service.selection_record("finnhub"))

    retried = service.retry_pending_revocation("finnhub")
    assert retried.is_authorized is False
    assert fake_keyring.items == {}


def test_凭据操作拒绝非finnhub和非钥匙串存储() -> None:
    """新浪、未知源及非系统钥匙串都不能创建、删除或伪造授权状态。"""

    from stock_agent.adapters.platform.credential_store import ReferenceCredentialStore
    from stock_agent.application.data_source_credential_service import (
        CredentialRegistration,
        DataSourceCredentialService,
    )

    service = DataSourceCredentialService(ReferenceCredentialStore())

    with pytest.raises(ValueError):
        service.configure(CredentialRegistration("sina", "test-secret"))
    with pytest.raises(ValueError):
        service.configure(CredentialRegistration("unknown", "test-secret"))
    with pytest.raises(ValueError):
        service.configure(CredentialRegistration("finnhub", "test-secret"))
    with pytest.raises(ValueError):
        service.revoke("sina")
    with pytest.raises(ValueError):
        service.revoke("unknown")
    with pytest.raises(ValueError):
        service.status("unknown")
    with pytest.raises(ValueError):
        service.selection_record("unknown")


def test_页面只接受脱敏选择记录() -> None:
    """页面不能从授权对象推断状态，避免密钥引用进入渲染路径。"""

    from stock_agent.desktop.pages.data_source_page import DataSourcePageState

    assert not hasattr(DataSourcePageState, "from_authorization")
