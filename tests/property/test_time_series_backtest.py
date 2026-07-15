"""验证时间序列回测切分不泄漏未来数据。"""

from datetime import date

import pytest


def test_滚动窗口训练验证按时间顺序且标签观察期隔离() -> None:
    """验证集标签观察期结束前，不得进入下一轮训练特征。"""

    from stock_agent.application.time_series_splitter import TimeSeriesSplitter

    splitter = TimeSeriesSplitter(
        mode="rolling",
        train_window_days=60,
        validation_window_days=10,
        label_horizon_days=5,
    )

    windows = splitter.split(start=date(2026, 1, 1), end=date(2026, 4, 30))

    assert windows[0].train_start < windows[0].train_end < windows[0].validation_start
    assert windows[0].validation_end < windows[1].train_start
    assert windows[0].label_available_at <= windows[1].train_start


def test_扩展窗口训练起点固定且验证向前滚动() -> None:
    """扩展窗口只能增加历史训练数据，不能打乱时间顺序。"""

    from stock_agent.application.time_series_splitter import TimeSeriesSplitter

    splitter = TimeSeriesSplitter(
        mode="expanding",
        train_window_days=60,
        validation_window_days=10,
        label_horizon_days=5,
    )

    first, second = splitter.split(start=date(2026, 1, 1), end=date(2026, 4, 30))[:2]

    assert first.train_start == second.train_start
    assert first.train_end < second.train_end
    assert first.validation_end < second.validation_end


def test_预测时点之后才可获得的特征会被拒绝() -> None:
    """任何预测时点不可获得的特征都必须触发未来数据泄漏错误。"""

    from stock_agent.application.time_series_splitter import PointInTimeFeatureGuard

    guard = PointInTimeFeatureGuard(prediction_date=date(2026, 7, 15))

    guard.validate_feature_available("close_t_minus_1", available_at=date(2026, 7, 14))

    with pytest.raises(ValueError, match="未来数据泄漏"):
        guard.validate_feature_available("future_close", available_at=date(2026, 7, 16))
