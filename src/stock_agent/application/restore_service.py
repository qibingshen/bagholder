"""隔离恢复、只读校验和用户确认后的原子切换。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RestoreSession:
    """跟踪一次备份恢复会话。"""

    backup_id: str
    staging_directory: str
    status: str = "staged"
    readonly_verified: bool = False
    user_confirmed: bool = False
    can_atomic_switch: bool = False
    can_resume_from_staging: bool = False

    def mark_interrupted(self) -> None:
        """恢复中断后只能从隔离目录继续。"""

        self.status = "interrupted"
        self.can_atomic_switch = False
        self.can_resume_from_staging = True

    def mark_readonly_verified(self) -> None:
        """记录只读校验完成。"""

        self.readonly_verified = True

    def confirm_user_switch(self) -> None:
        """用户确认后才允许原子切换。"""

        self.user_confirmed = True
        self.can_atomic_switch = self.readonly_verified
