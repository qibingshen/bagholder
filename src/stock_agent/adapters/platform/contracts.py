"""跨平台路径与安全凭据存储的边界契约。"""

from pathlib import Path
from typing import Protocol


class PlatformPaths(Protocol):
    """提供由平台实现决定的本地目录，避免把路径规则散落在业务代码中。"""

    def data_root(self) -> Path:
        """返回可保存本地量化事实的根目录。"""


class CredentialStore(Protocol):
    """仅保存安全存储引用；调用方不得取得或记录明文凭据。"""

    def put(self, source_id: str, secret: str) -> str:
        """保存凭据并返回不含密钥内容的引用标识。"""

    def delete(self, reference: str) -> None:
        """撤销凭据引用对应的安全存储项。"""
