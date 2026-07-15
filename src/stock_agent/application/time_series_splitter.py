"""时间序列回测切分和点时特征可用性校验。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

SplitMode = Literal["rolling", "expanding"]


@dataclass(frozen=True)
class TimeSeriesWindow:
    """单个时间序列回测窗口。"""

    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    label_available_at: date


class TimeSeriesSplitter:
    """生成滚动或扩展窗口，确保标签观察期隔离。"""

    def __init__(
        self,
        mode: SplitMode,
        train_window_days: int,
        validation_window_days: int,
        label_horizon_days: int,
    ) -> None:
        """初始化窗口参数。"""

        self._mode = mode
        self._train_window_days = train_window_days
        self._validation_window_days = validation_window_days
        self._label_horizon_days = label_horizon_days

    def split(self, start: date, end: date) -> tuple[TimeSeriesWindow, ...]:
        """生成不泄漏标签观察期的回测窗口。"""

        windows: list[TimeSeriesWindow] = []
        train_start = start
        train_end = start + timedelta(days=self._train_window_days - 1)
        while True:
            validation_start = train_end + timedelta(days=1)
            validation_end = validation_start + timedelta(days=self._validation_window_days - 1)
            label_available_at = validation_end + timedelta(days=self._label_horizon_days)
            if label_available_at > end:
                break
            windows.append(
                TimeSeriesWindow(
                    train_start=train_start,
                    train_end=train_end,
                    validation_start=validation_start,
                    validation_end=validation_end,
                    label_available_at=label_available_at,
                )
            )
            next_train_start = label_available_at
            if self._mode == "rolling":
                train_start = next_train_start
                latest_train_end = end - timedelta(
                    days=self._validation_window_days + self._label_horizon_days
                )
                if train_start > latest_train_end:
                    break
                train_end = min(
                    train_start + timedelta(days=self._train_window_days - 1),
                    latest_train_end,
                )
            else:
                train_end = label_available_at + timedelta(days=self._validation_window_days - 1)
        return tuple(windows)


class PointInTimeFeatureGuard:
    """校验特征是否在预测时点已经可获得。"""

    def __init__(self, prediction_date: date) -> None:
        """保存预测时点。"""

        self._prediction_date = prediction_date

    def validate_feature_available(self, feature_name: str, available_at: date) -> None:
        """预测时点之后才可获得的特征必须拒绝。"""

        if available_at > self._prediction_date:
            raise ValueError(f"未来数据泄漏：{feature_name}")
