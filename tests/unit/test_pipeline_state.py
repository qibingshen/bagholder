import pytest


def test_不能从等待审批跳过执行直接对账() -> None:
    from bagholder.domain.pipeline import PipelineState, ensure_transition

    with pytest.raises(ValueError, match="非法状态转移"):
        ensure_transition(PipelineState.WAITING_APPROVAL, PipelineState.RECONCILED)


def test_等待审批可以进入模拟成交或实盘提交() -> None:
    from bagholder.domain.pipeline import PipelineState, ensure_transition

    ensure_transition(PipelineState.WAITING_APPROVAL, PipelineState.PAPER_EXECUTED)
    ensure_transition(PipelineState.WAITING_APPROVAL, PipelineState.LIVE_SUBMITTED)

