"""管理受控数据源授权，确保公开状态、审计和页面不携带密钥或钥匙串引用。"""

from dataclasses import dataclass
from types import MappingProxyType

from stock_agent.adapters.platform.credential_store import (
    CredentialStore,
    KeyringCredentialStore,
)


@dataclass(frozen=True, slots=True)
class CredentialRegistration:
    """接收短生命周期的密钥输入，仅允许由 Finnhub 配置路径消费。"""

    source_id: str
    secret: str

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.secret:
            raise ValueError("数据源与凭据不能为空")


@dataclass(frozen=True, slots=True)
class CredentialAuthorization:
    """面向普通调用方的脱敏授权状态，不包含密钥或钥匙串引用。"""

    source_id: str
    is_authorized: bool


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
    """协调受控数据源与系统钥匙串，公开接口只返回脱敏状态。"""

    def __init__(self, credential_store: CredentialStore) -> None:
        self._credential_store = credential_store
        self._credential_references: dict[str, str] = {}

    def configure(self, registration: CredentialRegistration) -> CredentialAuthorization:
        """仅通过系统钥匙串配置 Finnhub，并返回不含引用的授权状态。"""

        self._require_finnhub_credential_operation(registration.source_id)
        if not isinstance(self._credential_store, KeyringCredentialStore):
            raise ValueError("Finnhub 凭据必须使用系统钥匙串存储")

        previous_reference = self._credential_references.get(registration.source_id)
        if previous_reference is not None:
            self._credential_store.delete(previous_reference)
        self._credential_references[registration.source_id] = self._credential_store.put(
            registration.source_id, registration.secret
        )
        return CredentialAuthorization(registration.source_id, is_authorized=True)

    def revoke(self, source_id: str) -> CredentialAuthorization:
        """仅撤销 Finnhub 的内部钥匙串引用并返回脱敏受限状态。"""

        self._require_finnhub_credential_operation(source_id)
        previous_reference = self._credential_references.pop(source_id, None)
        if previous_reference is not None:
            self._credential_store.delete(previous_reference)
        return CredentialAuthorization(source_id, is_authorized=False)

    def status(self, source_id: str) -> CredentialAuthorization:
        """查询受控数据源的脱敏状态；未知数据源明确失败。"""

        metadata = self._metadata_for(source_id)
        if not metadata.requires_credentials:
            return CredentialAuthorization(source_id, is_authorized=True)
        return CredentialAuthorization(
            source_id, is_authorized=source_id in self._credential_references
        )

    def selection_record(self, source_id: str) -> DataSourceSelectionRecord:
        """返回可审计的选择状态，永不携带凭据或钥匙串引用。"""

        metadata = self._metadata_for(source_id)
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

    @staticmethod
    def _metadata_for(source_id: str) -> DataSourceMetadata:
        metadata = DATA_SOURCE_METADATA.get(source_id)
        if metadata is None:
            raise ValueError("不支持的数据源")
        return metadata

    def _require_finnhub_credential_operation(self, source_id: str) -> None:
        self._metadata_for(source_id)
        if source_id != "finnhub":
            raise ValueError("仅 Finnhub 支持凭据操作")
