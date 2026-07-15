"""组装预测详情页工作区，阻断不可用当前预测。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from stock_agent.application.prediction_presenter import PredictionPresentation
from stock_agent.desktop.pages.prediction_page import PredictionDetailView, PredictionPageState


@dataclass(frozen=True, slots=True)
class PredictionWorkspaceModel:
    """预测页面工作区模型，区分当前预测和历史只读快照。"""

    page_state: PredictionPageState
    current_detail: PredictionDetailView | None
    historical_details: tuple[PredictionDetailView, ...]
    current_prediction_allowed: bool


class PredictionController:
    """只编排已生成的本地预测展示结果，不生成或修改预测数字。"""

    def build_workspace(
        self,
        *,
        current_prediction: PredictionPresentation | None,
        historical_predictions: Iterable[PredictionPresentation],
        permission_granted: bool = True,
    ) -> PredictionWorkspaceModel:
        """根据权限和新鲜度决定当前预测入口与历史快照展示。"""

        if not permission_granted:
            page_state = PredictionPageState(status="PERMISSION_DENIED")
            return PredictionWorkspaceModel(page_state, None, (), False)

        historical_details = tuple(
            PredictionDetailView.from_presentation(item, historical=True)
            for item in historical_predictions
        )
        if current_prediction is None:
            page_state = PredictionPageState(
                status="HISTORICAL_SNAPSHOT" if historical_details else "EMPTY"
            )
            return PredictionWorkspaceModel(page_state, None, historical_details, False)

        current_detail = PredictionDetailView.from_presentation(current_prediction)
        if current_detail.page_state.status != "READY":
            return PredictionWorkspaceModel(
                current_detail.page_state,
                None,
                historical_details,
                False,
            )
        return PredictionWorkspaceModel(
            current_detail.page_state,
            current_detail,
            historical_details,
            current_detail.page_state.allow_current_prediction,
        )
