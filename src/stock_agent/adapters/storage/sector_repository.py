"""板块与成员有效区间的本地仓储。"""

from __future__ import annotations

from dataclasses import dataclass, field

from stock_agent.domain.sector import CustomSector, Sector


@dataclass
class InMemorySectorRepository:
    """用于首个实现闭环的板块仓储，保持追加式写入语义。"""

    _sectors: dict[str, Sector] = field(default_factory=dict)
    _custom_sectors: dict[str, CustomSector] = field(default_factory=dict)

    def save_sector(self, sector: Sector) -> None:
        """保存主要板块定义；调用方必须提供带版本的完整成员有效期。"""

        self._sectors[sector.sector_id] = sector

    def get_sector(self, sector_id: str) -> Sector:
        """读取主要板块定义。"""

        return self._sectors[sector_id]

    def save_custom_sector(self, custom_sector: CustomSector) -> None:
        """保存自定义板块追加式变更历史。"""

        self._custom_sectors[custom_sector.sector_id] = custom_sector

    def get_custom_sector(self, sector_id: str) -> CustomSector:
        """读取自定义板块变更历史。"""

        return self._custom_sectors[sector_id]
