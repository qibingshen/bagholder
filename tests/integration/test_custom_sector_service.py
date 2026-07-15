"""验证自定义板块用例保持追加式成员历史。"""

from datetime import date


def test_自定义板块服务创建归档并追加成员变更() -> None:
    """用户维护自定义板块时，成员变化必须追加记录而不是覆盖。"""

    from stock_agent.adapters.storage.sector_repository import InMemorySectorRepository
    from stock_agent.application.custom_sector_service import CustomSectorService

    repository = InMemorySectorRepository()
    service = CustomSectorService(repository=repository)

    service.create_sector(sector_id="custom-1", name="观察池", created_at=date(2026, 7, 10))
    service.add_member(
        sector_id="custom-1",
        security_key="CN:600000.SH",
        effective_date=date(2026, 7, 11),
        source="user",
    )
    service.remove_member(
        sector_id="custom-1",
        security_key="CN:600000.SH",
        effective_date=date(2026, 7, 15),
        source="user",
    )
    service.archive_sector(sector_id="custom-1", archived_at=date(2026, 7, 20))

    custom_sector = repository.get_custom_sector("custom-1")

    assert custom_sector.archived_at == date(2026, 7, 20)
    assert [change.action for change in custom_sector.changes] == ["add", "remove"]
    assert [change.change_id for change in custom_sector.changes] == [
        "custom-1-000001",
        "custom-1-000002",
    ]
