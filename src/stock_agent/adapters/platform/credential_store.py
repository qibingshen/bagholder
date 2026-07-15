"""定义凭据保险库边界，业务层只能取得引用，不能读取或记录明文密钥。"""

from typing import Any, Protocol
from uuid import uuid4


class CredentialStore(Protocol):
    """平台安全存储的最小接口，返回值只能是可撤销的引用。"""

    def put(self, source_id: str, secret: str) -> str:
        """保存明文凭据并返回引用。"""

    def delete(self, reference: str) -> None:
        """撤销引用所指向的凭据。"""


class ReferenceCredentialStore:
    """仅用于测试的内存保险库；生产启动器必须注入真实平台保险库。"""

    def __init__(self) -> None:
        self._items: dict[str, str] = {}

    def put(self, source_id: str, secret: str) -> str:
        """以不可预测引用保存测试凭据，业务输出不包含其明文。"""

        reference = f"platform-keychain://{source_id}/{uuid4()}"
        self._items[reference] = secret
        return reference

    def delete(self, reference: str) -> None:
        """从测试保险库移除已撤销凭据。"""

        self._items.pop(reference, None)


class KeyringCredentialStore:
    """通过系统钥匙串保存生产凭据，业务层只能得到可撤销引用。"""

    def __init__(
        self, service_name: str = "local-stock-agent", keyring_backend: Any | None = None
    ) -> None:
        if keyring_backend is None:
            try:
                import keyring
            except ImportError as error:
                raise RuntimeError("未安装系统凭据保险库依赖，不能配置数据源凭据") from error
            keyring_backend = keyring
        self._service_name = service_name
        self._keyring = keyring_backend

    def put(self, source_id: str, secret: str) -> str:
        """把明文交给系统保险库，应用数据库仅记录生成的引用。"""

        reference = f"platform-keychain://{source_id}/{uuid4()}"
        self._keyring.set_password(self._service_name, reference, secret)
        return reference

    def delete(self, reference: str) -> None:
        """撤销系统保险库中的引用；未找到项由平台后端按其语义处理。"""

        self._keyring.delete_password(self._service_name, reference)
