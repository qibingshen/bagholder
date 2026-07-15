"""验证候选模型影子运行证据累积。"""

from datetime import date


def test_影子运行累积_30_个交易日后才满足证据门槛() -> None:
    """候选模型必须和正式模型并行影子运行至少 30 个交易日。"""

    from stock_agent.training.shadow_runner import ShadowRunEvidence

    evidence = ShadowRunEvidence(
        candidate_model_version="candidate-v1", active_model_version="baseline-v1"
    )
    for offset in range(30):
        evidence.record_day(trade_date=date(2026, 6, 1 + offset), result_id=f"shadow-{offset}")

    assert evidence.trading_days == 30
    assert evidence.ready_for_release_gate is True
