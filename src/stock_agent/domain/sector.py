"""定义板块、成员有效期、指标和自定义板块变更契约。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SectorCategory = Literal["industry", "concept", "region"]
MarketCode = Literal["CN", "HK", "US"]
SectorMemberAction = Literal["add", "remove"]


class SectorMember(BaseModel):
    """板块成员在指定时间区间内有效。"""

    security_key: str = Field(min_length=1)
    valid_from: date
    valid_to: date | None = None
    weight: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))

    @model_validator(mode="after")
    def 验证成员有效区间(self) -> SectorMember:
        """成员结束日期不得早于开始日期。"""

        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("成员有效期结束日期不得早于开始日期")
        return self


class Sector(BaseModel):
    """主要板块定义，保留市场、币种、来源和成员有效期。"""

    sector_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: SectorCategory
    market: MarketCode
    currency: str = Field(min_length=3, max_length=3)
    source_id: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    members: list[SectorMember]


class SectorMetrics(BaseModel):
    """板块总览指标，覆盖涨跌、活跃度、家数、趋势、轮动和覆盖率。"""

    sector_id: str = Field(min_length=1)
    as_of: date
    return_pct: Decimal
    turnover_activity: Decimal = Field(ge=Decimal("0"))
    advancing_count: int = Field(ge=0)
    declining_count: int = Field(ge=0)
    trend_strength: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    rotation_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    coverage_ratio: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    data_version: str = Field(min_length=1)


class SectorMemberChange(BaseModel):
    """自定义板块成员追加式变更记录。"""

    change_id: str = Field(min_length=1)
    security_key: str = Field(min_length=1)
    action: SectorMemberAction
    effective_date: date
    source: str = Field(min_length=1)


class CustomSector(BaseModel):
    """用户自定义板块，成员变化只能以变更记录追加。"""

    sector_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    created_at: date
    archived_at: date | None = None
    changes: list[SectorMemberChange]

    @model_validator(mode="after")
    def 验证归档时间(self) -> CustomSector:
        """归档时间不得早于创建时间。"""

        if self.archived_at is not None and self.archived_at < self.created_at:
            raise ValueError("自定义板块归档时间不得早于创建时间")
        return self
