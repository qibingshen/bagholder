"""验证预测快照仓储追加保存、版本索引和到期结果回填边界。"""

from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from stock_agent.adapters.storage.prediction_repository import (
    PredictionRepository,
    PredictionRepositoryError,
)
from stock_agent.application.prediction_service import (
    FeatureSnapshotFact,
    PredictionGenerationCommand,
    PredictionService,
)
from stock_agent.domain.market import InstrumentIdentity, Market
from stock_agent.domain.market_rules import TradingCalendar
from stock_agent.domain.prediction import (
    ActualOutcomeStatus,
    ImmutablePredictionSnapshotError,
    PredictionLabelRule,
    PredictionSnapshotStore,
    issue_local_outcome_fact,
    outcome_fact_value,
    resolve_actual_outcome,
)

预测时点 = datetime(2026, 7, 14, 20, 0, tzinfo=UTC)
证券 = InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD")
日历 = TradingCalendar(
    market="US",
    version_id="calendar-us-v1",
    trading_days=frozenset({date(2026, 7, 14), date(2026, 7, 15), date(2026, 7, 16)}),
)
标签规则 = PredictionLabelRule(
    version_id="prediction-label-v1",
    thresholds={1: Decimal("0.01"), 5: Decimal("0.03"), 20: Decimal("0.06")},
)


def 生成快照():
    """通过应用服务生成真实领域快照，避免测试绕过 T051 用例。"""

    store = PredictionSnapshotStore()
    service = PredictionService(snapshot_store=store)
    command = PredictionGenerationCommand(
        security_id=证券,
        predicted_at=预测时点,
        market_time=datetime(2026, 7, 14, 16, 0, tzinfo=UTC),
        collected_at=datetime(2026, 7, 14, 16, 5, tzinfo=UTC),
        available_at=datetime(2026, 7, 14, 16, 10, tzinfo=UTC),
        source_id="local-daily-bars",
        data_version="daily-us-v1",
        model_version="baseline-v1",
        horizon_trading_days=1,
        freshness="NEAR_REALTIME",
        reference_total_return_adjusted_price=Decimal("100"),
        reference_price_available_at=datetime(2026, 7, 14, 16, 10, tzinfo=UTC),
        trading_calendar=日历,
        calendar_available_at=datetime(2026, 7, 14, 8, 0, tzinfo=UTC),
        prediction_label_rule=标签规则,
        label_rule_available_at=datetime(2026, 7, 14, 8, 0, tzinfo=UTC),
        feature_snapshot=FeatureSnapshotFact(
            snapshot_id="feature:US:NASDAQ:AAPL:2026-07-14",
            security_id=证券,
            feature_version="features-v1",
            source_id="local-feature-store",
            market_time=datetime(2026, 7, 14, 16, 0, tzinfo=UTC),
            collected_at=datetime(2026, 7, 14, 16, 5, tzinfo=UTC),
            available_at=datetime(2026, 7, 14, 16, 10, tzinfo=UTC),
            cutoff_at=datetime(2026, 7, 14, 16, 0, tzinfo=UTC),
            values={"five_day_momentum": Decimal("0.012")},
        ),
        primary_evidence=("本地特征快照已按预测时点截断",),
        risk_factors=("简单基准存在模型偏差",),
    )
    return service.generate_simple_baseline_snapshot(command)


def 有效到期结果(snapshot_id: str):
    """构造可回填的到期实际结果及完整签名事实。"""

    validated_at = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    expiry_time = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)
    facts = {
        "REFERENCE_PRICE": Decimal("100"),
        "EXPIRY_PRICE": Decimal("101"),
        "REFERENCE_TRADABILITY": "TRADABLE",
        "EXPIRY_TRADABILITY": "TRADABLE",
        "TRADING_CALENDAR": 日历,
        "LABEL_RULE": 标签规则,
        "COMPANY_ACTIONS": (),
    }
    versions = {
        "REFERENCE_PRICE": "daily-us-v1",
        "EXPIRY_PRICE": "daily-us-v1",
        "REFERENCE_TRADABILITY": "daily-us-v1",
        "EXPIRY_TRADABILITY": "daily-us-v1",
        "TRADING_CALENDAR": 日历.version_id,
        "LABEL_RULE": 标签规则.version_id,
        "COMPANY_ACTIONS": "company-actions-v1",
    }
    references = tuple(
        issue_local_outcome_fact(
            fact_type=fact_type,
            security_id=证券,
            prediction_snapshot_id=snapshot_id,
            prediction_time=预测时点,
            reference_type="LOCAL",
            source_id="local-verified-history",
            tool_name="local_fact_store",
            tool_version="v1",
            market_time=(
                预测时点
                if fact_type == "REFERENCE_PRICE"
                else expiry_time
                if fact_type == "EXPIRY_PRICE"
                else validated_at
            ),
            collected_at=(
                预测时点
                if fact_type == "REFERENCE_PRICE"
                else expiry_time
                if fact_type == "EXPIRY_PRICE"
                else validated_at
            ),
            available_at=(
                预测时点
                if fact_type == "REFERENCE_PRICE"
                else expiry_time
                if fact_type == "EXPIRY_PRICE"
                else validated_at
            ),
            version_id=versions[fact_type],
            result_id=f"{fact_type}:{versions[fact_type]}",
            result_anchor=f"local://outcomes/{fact_type}:{versions[fact_type]}",
            fact_value=outcome_fact_value(fact_type, value),
            value_hash=sha256(
                f"{fact_type}:{outcome_fact_value(fact_type, value)}".encode()
            ).hexdigest(),
        )
        for fact_type, value in facts.items()
    )
    return resolve_actual_outcome(
        prediction_snapshot_id=snapshot_id,
        prediction_time=预测时点,
        horizon_trading_days=1,
        reference_trading_day=date(2026, 7, 14),
        expiry_trading_day=date(2026, 7, 15),
        trading_calendar=日历,
        trading_calendar_version=日历.version_id,
        reference_total_return_adjusted_price=Decimal("100"),
        expiry_total_return_adjusted_price=Decimal("101"),
        expiry_price_available_at=expiry_time,
        validated_at=validated_at,
        prediction_label_rule=标签规则,
        outcome_fact_references=references,
        security_id=证券,
        price_data_version="daily-us-v1",
    )


def test_预测仓储追加保存快照并可按版本索引查询(local_data_root: Path) -> None:
    """快照落库后必须能查回模型、特征、数据和规则版本关联。"""

    repository = PredictionRepository(local_data_root / "prediction.duckdb")
    snapshot = 生成快照()

    repository.append_snapshot(snapshot)
    record = repository.get_snapshot_record(snapshot.snapshot_id)

    assert record.snapshot_id == snapshot.snapshot_id
    assert record.data_version == "daily-us-v1"
    assert record.feature_version == "features-v1"
    assert record.model_version == "baseline-v1"
    assert record.label_rule_version == "prediction-label-v1"
    assert record.trading_calendar_version == "calendar-us-v1"
    assert record.horizon_trading_days == 1


def test_预测仓储拒绝覆盖同一快照(local_data_root: Path) -> None:
    """预测快照是追加事实，同一标识不能静默覆盖。"""

    repository = PredictionRepository(local_data_root / "prediction.duckdb")
    snapshot = 生成快照()
    repository.append_snapshot(snapshot)

    with pytest.raises(PredictionRepositoryError, match="追加|覆盖|重复"):
        repository.append_snapshot(snapshot)


def test_预测仓储仅在领域复验通过后回填已验证到期结果(local_data_root: Path) -> None:
    """到期结果必须绑定原快照，且待验证结果不得落库。"""

    repository = PredictionRepository(local_data_root / "prediction.duckdb")
    snapshot = 生成快照()
    repository.append_snapshot(snapshot)
    outcome = 有效到期结果(snapshot.snapshot_id)

    stored = repository.append_actual_outcome(outcome)

    assert stored.status is ActualOutcomeStatus.VALIDATED
    assert repository.actual_outcomes_for(snapshot.snapshot_id) == (stored,)
    with pytest.raises(ImmutablePredictionSnapshotError, match="追加|重复|覆盖"):
        repository.append_actual_outcome(outcome)
