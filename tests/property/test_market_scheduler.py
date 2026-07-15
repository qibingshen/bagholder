"""验证三大市场每日任务调度规则。"""

from datetime import date


def test_三大市场默认每日任务时点使用各自市场时区() -> None:
    """A 股、港股、美股必须按各自市场时区生成开盘前、盘中和收盘后任务。"""

    from stock_agent.application.daily_scheduler import DailyScheduler, MarketScheduleConfig

    scheduler = DailyScheduler(
        configs=[
            MarketScheduleConfig.default_for("CN"),
            MarketScheduleConfig.default_for("HK"),
            MarketScheduleConfig.default_for("US"),
        ]
    )

    runs = scheduler.schedule_for(date(2026, 7, 15))

    assert [(run.market, run.phase, run.local_time.strftime("%H:%M")) for run in runs] == [
        ("CN", "pre_open", "08:45"),
        ("CN", "intraday", "11:45"),
        ("CN", "post_close", "15:30"),
        ("HK", "pre_open", "08:45"),
        ("HK", "intraday", "12:30"),
        ("HK", "post_close", "16:30"),
        ("US", "pre_open", "08:45"),
        ("US", "intraday", "12:30"),
        ("US", "post_close", "16:30"),
    ]


def test_休市日不生成每日任务() -> None:
    """休市日不能误触发行情更新、回测或报告。"""

    from stock_agent.application.daily_scheduler import DailyScheduler, MarketScheduleConfig

    scheduler = DailyScheduler(
        configs=[MarketScheduleConfig.default_for("CN")], holidays={"CN": {date(2026, 10, 1)}}
    )

    assert scheduler.schedule_for(date(2026, 10, 1)) == ()


def test_半日市使用提前收盘后的报告时点() -> None:
    """半日市必须在提前收盘后生成收盘后报告。"""

    from stock_agent.application.daily_scheduler import DailyScheduler, MarketScheduleConfig

    scheduler = DailyScheduler(
        configs=[MarketScheduleConfig.default_for("HK")],
        half_days={"HK": {date(2026, 12, 24): "12:30"}},
    )

    runs = scheduler.schedule_for(date(2026, 12, 24))

    assert [run.local_time.strftime("%H:%M") for run in runs] == ["08:45", "11:30", "13:00"]


def test_美股夏令时和冬令时都保留纽约市场时区() -> None:
    """美股调度以纽约市场时区表示，本地存储保留时区，避免 DST 漂移。"""

    from stock_agent.application.daily_scheduler import DailyScheduler, MarketScheduleConfig

    scheduler = DailyScheduler(configs=[MarketScheduleConfig.default_for("US")])

    summer = scheduler.schedule_for(date(2026, 7, 15))[0].local_time
    winter = scheduler.schedule_for(date(2026, 12, 15))[0].local_time

    assert summer.tzinfo is not None
    assert winter.tzinfo is not None
    assert summer.strftime("%H:%M") == "08:45"
    assert winter.strftime("%H:%M") == "08:45"
    assert summer.utcoffset() != winter.utcoffset()
