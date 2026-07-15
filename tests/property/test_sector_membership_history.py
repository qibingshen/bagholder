"""验证板块成员历史按时间点查询。"""

from datetime import date


def test_自定义板块按时间点返回当时有效成员() -> None:
    """历史分析必须使用当时有效成员，不能用当前成员倒灌过去。"""

    from stock_agent.domain.sector_membership import SectorMembershipTimeline

    timeline = SectorMembershipTimeline(sector_id="custom-watchlist-1")
    timeline.add_member("US:AAPL", effective_date=date(2026, 7, 10), source="user")
    timeline.add_member("HK:00700", effective_date=date(2026, 7, 12), source="user")
    timeline.remove_member("US:AAPL", effective_date=date(2026, 7, 15), source="user")

    assert timeline.members_at(date(2026, 7, 11)) == frozenset({"US:AAPL"})
    assert timeline.members_at(date(2026, 7, 13)) == frozenset({"US:AAPL", "HK:00700"})
    assert timeline.members_at(date(2026, 7, 16)) == frozenset({"HK:00700"})


def test_成员历史保留跨市场证券键且不合并同名代码() -> None:
    """A 股、港股和美股代码命名空间不同，成员查询不得只按代码数字合并。"""

    from stock_agent.domain.sector_membership import SectorMembershipTimeline

    timeline = SectorMembershipTimeline(sector_id="custom-cross-market")
    timeline.add_member("CN:600000.SH", effective_date=date(2026, 7, 10), source="user")
    timeline.add_member("HK:600000", effective_date=date(2026, 7, 10), source="user")
    timeline.add_member("US:600000", effective_date=date(2026, 7, 10), source="user")

    assert timeline.members_at(date(2026, 7, 11)) == frozenset(
        {"CN:600000.SH", "HK:600000", "US:600000"}
    )


def test_成员变更历史为追加记录并可导出审计序列() -> None:
    """成员增删必须形成追加式历史，便于复盘和数据版本追溯。"""

    from stock_agent.domain.sector_membership import SectorMembershipTimeline

    timeline = SectorMembershipTimeline(sector_id="custom-watchlist-1")
    timeline.add_member("CN:600000.SH", effective_date=date(2026, 7, 10), source="user")
    timeline.remove_member("CN:600000.SH", effective_date=date(2026, 7, 15), source="user")

    audit = timeline.audit_trail()

    assert [event.action for event in audit] == ["add", "remove"]
    assert [event.sequence for event in audit] == [1, 2]
