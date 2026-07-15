"""备份清单和恢复计划契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

PlatformName = Literal["Windows", "Darwin", "Linux"]


class BackupManifestItem(BaseModel):
    """备份清单中的单个文件条目。"""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    size_bytes: int = Field(ge=0)


class BackupManifest(BaseModel):
    """备份包清单，包含版本链、平台和文件哈希。"""

    backup_id: str = Field(min_length=1)
    created_on_platform: PlatformName
    app_version: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    parent_backup_id: str | None = None
    items: tuple[BackupManifestItem, ...]

    @computed_field
    @property
    def total_size_bytes(self) -> int:
        """计算备份包总大小。"""

        return sum(item.size_bytes for item in self.items)


class RestorePlan(BaseModel):
    """恢复计划，要求隔离校验和用户确认后原子切换。"""

    backup_id: str = Field(min_length=1)
    target_platform: PlatformName
    staging_directory: str = Field(min_length=1)
    readonly_verified: bool
    requires_user_confirmation: bool
    atomic_switch: bool

    @model_validator(mode="after")
    def 验证恢复安全门禁(self) -> RestorePlan:
        """恢复必须先只读校验、需要用户确认，并使用原子切换。"""

        if not self.readonly_verified:
            raise ValueError("恢复计划必须先完成只读校验")
        if not self.requires_user_confirmation:
            raise ValueError("恢复计划必须需要用户确认")
        if not self.atomic_switch:
            raise ValueError("恢复计划必须使用原子切换")
        return self
