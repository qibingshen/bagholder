"""验证新浪和 Finnhub 的受控配置、公开状态与页面脱敏边界。"""

import pytest


class FakeKeyring:
    """记录系统钥匙串调用，供受控配置路径验收使用。"""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.items[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
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
