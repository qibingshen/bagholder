"""验证所有量化结果共享的元数据与脱敏错误契约。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_结果信封保留量化数字的完整溯源元数据() -> None:
    """缺少来源、市场时间、采集时间或数据版本的数字不能成为可展示事实。"""

    from stock_agent.contracts.common import Freshness, ResultEnvelope, SourceProvenance

    result = ResultEnvelope[dict[str, float]](
        contract_version="1.0",
        result_id=uuid4(),
        request_id=uuid4(),
        generated_at=datetime(2026, 7, 14, tzinfo=UTC),
        data_as_of=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        data_version="daily-cn-v1",
        freshness=Freshness(state="REALTIME", age_seconds=5),
        provenance=[
            SourceProvenance(
                source_id="test-source",
                market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
                collected_at=datetime(2026, 7, 14, 9, 30, 5, tzinfo=UTC),
                data_version="daily-cn-v1",
                artifact_hash="a" * 64,
            )
        ],
        payload={"close": 10.0},
    )

    assert result.provenance[0].data_version == result.data_version


def test_结果信封拒绝没有溯源的量化负载() -> None:
    """溯源列表为空时必须在进入界面或大模型之前失败。"""

    from stock_agent.contracts.common import Freshness, ResultEnvelope

    with pytest.raises(ValidationError):
        ResultEnvelope[dict[str, float]](
            contract_version="1.0",
            result_id=uuid4(),
            request_id=uuid4(),
            generated_at=datetime(2026, 7, 14, tzinfo=UTC),
            data_as_of=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            data_version="daily-cn-v1",
            freshness=Freshness(state="REALTIME", age_seconds=5),
            provenance=[],
            payload={"close": 10.0},
        )
