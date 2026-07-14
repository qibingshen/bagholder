"""管理数据源授权引用，确保明文凭据不进入领域记录、日志或桌面状态。"""

from dataclasses import dataclass
from types import MappingProxyType

from stock_agent.adapters.platform.credential_store import CredentialStore


@dataclass(frozen=True, slots=True)
class CredentialRegistration:
    """接收待保存凭据的短生命周期输入。"""

    source_id: str
    secret: str

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.secret:
            raise ValueError("数据源与凭据不能为空")


@dataclass(frozen=True, slots=True)
class CredentialAuthorization:
    """可展示的授权状态，永不包含明文凭据。"""

    source_id: str
    credential_reference: str | None

    @property
    def is_authorized(self) -> bool:
        """只有存在可撤销引用时才允许数据源适配器请求受限数据。"""

        return self.credential_reference is not None


@dataclass(frozen=True, slots=True)
class DataSourceMetadata:
    """不可变的数据源配置，仅描述市场范围、授权边界和降级规则。"""

    source_id: str
    supported_markets: tuple[str, ...]
    requires_credentials: bool
    access_state: str
    degradation_notice: str


@dataclass(frozen=True, slots=True)
class DataSourceSelectionRecord:
    """可复核的数据源选择记录，不包含明文密钥或钥匙串引用。"""

    source_id: str
    supported_markets: tuple[str, ...]
    requires_credentials: bool
    access_state: str
    degradation_notice: str
    audit_note: str


DATA_SOURCE_METADATA = MappingProxyType(
    {
        "sina": DataSourceMetadata(
            source_id="sina",
            supported_markets=("CN",),
            requires_credentials=False,
            access_state="公开只读",
            degradation_notice="公开只读且不保证实时；仅作为 A 股候选数据源。",
        ),
        "finnhub": DataSourceMetadata(
            source_id="finnhub",
            supported_markets=("US",),
            requires_credentials=True,
            access_state="受限",
            degradation_notice="无密钥降级为受限状态，不提供美股实时数据。",
        ),
    }
)

_SELECTION_AUDIT_NOTES = MappingProxyType(
    {
        "sina": "新浪 URL 仅支持公开只读能力；受市场时间与数据新鲜度限制，不保证实时。",
        "finnhub": "Finnhub 由用户自带合法密钥；无密钥降级，数据源不混用且不绕过许可。",
    }
)


class DataSourceCredentialService:
    """协调安全保险库与可展示的授权状态，不向上层返回明文凭据。"""

    def __init__(self, credential_store: CredentialStore) -> None:
        self._credential_store = credential_store
        self._authorizations: dict[str, CredentialAuthorization] = {}

    def configure(self, registration: CredentialRegistration) -> CredentialAuthorization:
        """保存凭据并记录其引用；重新配置时先撤销旧引用。"""

        metadata = DATA_SOURCE_METADATA.get(registration.source_id)
        if metadata and not metadata.requires_credentials:
            raise ValueError("公开只读数据源不接受凭据配置")

        previous = self._authorizations.get(registration.source_id)
        if previous and previous.credential_reference:
            self._credential_store.delete(previous.credential_reference)
        reference = self._credential_store.put(registration.source_id, registration.secret)
        authorization = CredentialAuthorization(registration.source_id, reference)
        self._authorizations[registration.source_id] = authorization
        return authorization

    def revoke(self, source_id: str) -> CredentialAuthorization:
        """撤销数据源授权并保留受限状态，调用方必须触发明确的降级展示。"""

        previous = self._authorizations.pop(source_id, None)
        if previous and previous.credential_reference:
            self._credential_store.delete(previous.credential_reference)
        return CredentialAuthorization(source_id, None)

    def status(self, source_id: str) -> CredentialAuthorization:
        """返回授权或受限状态，不泄露保险库内部内容。"""

        return self._authorizations.get(source_id, CredentialAuthorization(source_id, None))

    def selection_record(self, source_id: str) -> DataSourceSelectionRecord:
        """返回可审计的选择状态，永不携带凭据或钥匙串引用。"""

        metadata = DATA_SOURCE_METADATA.get(source_id)
        if metadata is None:
            raise ValueError("不支持的数据源")

        access_state = metadata.access_state
        if metadata.requires_credentials and self.status(source_id).is_authorized:
            access_state = "已授权"

        return DataSourceSelectionRecord(
            source_id=metadata.source_id,
            supported_markets=metadata.supported_markets,
            requires_credentials=metadata.requires_credentials,
            access_state=access_state,
            degradation_notice=metadata.degradation_notice,
            audit_note=_SELECTION_AUDIT_NOTES[source_id],
        )
