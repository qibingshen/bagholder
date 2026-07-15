"""自定义板块创建、归档和追加式成员变更用例。"""

from __future__ import annotations

from datetime import date

from stock_agent.adapters.storage.sector_repository import InMemorySectorRepository
from stock_agent.domain.sector import CustomSector, SectorMemberChange


class CustomSectorService:
    """维护用户自定义板块，所有成员变化都以变更记录追加。"""

    def __init__(self, repository: InMemorySectorRepository) -> None:
        """注入板块仓储。"""

        self._repository = repository

    def create_sector(self, sector_id: str, name: str, created_at: date) -> CustomSector:
        """创建空的自定义板块。"""

        custom_sector = CustomSector(
            sector_id=sector_id,
            name=name,
            created_at=created_at,
            archived_at=None,
            changes=[],
        )
        self._repository.save_custom_sector(custom_sector)
        return custom_sector

    def archive_sector(self, sector_id: str, archived_at: date) -> CustomSector:
        """归档自定义板块，不删除历史成员变更。"""

        current = self._repository.get_custom_sector(sector_id)
        archived = CustomSector(
            sector_id=current.sector_id,
            name=current.name,
            created_at=current.created_at,
            archived_at=archived_at,
            changes=current.changes,
        )
        self._repository.save_custom_sector(archived)
        return archived

    def add_member(
        self,
        sector_id: str,
        security_key: str,
        effective_date: date,
        source: str,
    ) -> CustomSector:
        """追加成员加入记录。"""

        return self._append_change(sector_id, security_key, "add", effective_date, source)

    def remove_member(
        self,
        sector_id: str,
        security_key: str,
        effective_date: date,
        source: str,
    ) -> CustomSector:
        """追加成员移除记录。"""

        return self._append_change(sector_id, security_key, "remove", effective_date, source)

    def _append_change(
        self,
        sector_id: str,
        security_key: str,
        action: str,
        effective_date: date,
        source: str,
    ) -> CustomSector:
        """生成顺序变更编号并写回完整历史。"""

        current = self._repository.get_custom_sector(sector_id)
        sequence = len(current.changes) + 1
        change = SectorMemberChange(
            change_id=f"{sector_id}-{sequence:06d}",
            security_key=security_key,
            action=action,
            effective_date=effective_date,
            source=source,
        )
        updated = CustomSector(
            sector_id=current.sector_id,
            name=current.name,
            created_at=current.created_at,
            archived_at=current.archived_at,
            changes=[*current.changes, change],
        )
        self._repository.save_custom_sector(updated)
        return updated
