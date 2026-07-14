"""验证首个市场历史日线的本地闭环，不访问真实网络。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stock_agent.application.versioning_service import VersioningService
from stock_agent.domain.freshness import (
    FreshnessClassificationError,
    is_usable_for_current_prediction,
)
from stock_agent.domain.market import InstrumentIdentity, Market


def 固定历史日线响应() -> bytes:
    """返回固定的历史日线原始响应，防止集成测试触发任何真实网络请求。"""

    return json.dumps(
        {
            "bars": [
                {
                    "close": 10.20,
                    "high": 10.50,
                    "low": 9.80,
                    "open": 10.00,
                    "trade_date": "2026-07-13",
                    "volume": 1_000_000,
                }
            ],
            "response_schema_version": "固定历史日线响应-1",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def 创建工作者(读取历史日线, 服务: VersioningService):
    """延迟导入尚未实现的工作者，使红灯直接指向 US1 的生产缺口。"""

    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionWorker

    return HistoricalDailyIngestionWorker(
        read_historical_daily=读取历史日线,
        versioning_service=服务,
    )


def 采集参数() -> dict[str, object]:
    """返回固定的市场、证券和采集时间，确保工件关联可重复核。"""

    return {
        "collected_at": datetime(2026, 7, 14, 7, 1, 2, tzinfo=UTC),
        "security_id": InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
        "source_id": "sina",
    }


def test_历史日线将注入响应追加保存为原始与规范化工件并可按溯源字段回读(
    local_data_root: Path,
) -> None:
    """成功采集必须保留原文、日线、版本链和哈希，不能依赖真实新浪请求。"""

    请求参数: list[dict[str, object]] = []
    原始响应 = 固定历史日线响应()

    def 读取历史日线(**参数: object) -> bytes:
        请求参数.append(dict(参数))
        return 原始响应

    服务 = VersioningService(local_data_root)
    结果 = 创建工作者(读取历史日线, 服务).collect_and_save(**采集参数())

    assert 请求参数 == [采集参数()]
    assert 结果.bars[0].trade_date.isoformat() == "2026-07-13"
    assert 结果.bars[0].source_id == "sina"
    assert 结果.bars[0].freshness.state != "REALTIME"
    assert 服务.read_bytes("market-data-raw", 结果.raw_version_id) == 原始响应

    规范化工件 = 服务.read_bytes("market-data-normalized", 结果.normalized_version_id)
    规范化批次 = json.loads(规范化工件)
    元数据 = 服务.metadata_for("market-data-normalized", 结果.normalized_version_id)
    assert 规范化批次["source_id"] == "sina"
    assert 规范化批次["market"] == "CN"
    assert 规范化批次["collected_at"] == "2026-07-14T07:01:02+00:00"
    assert 规范化批次["bars"][0]["market_time"] == "2026-07-13T15:00:00+08:00"
    assert 规范化批次["bars"][0]["data_version"] == 结果.normalized_version_id
    assert 元数据["parent_version_id"] == 结果.raw_version_id
    assert 元数据["content_hash"] == hashlib.sha256(规范化工件).hexdigest()


def test_相同历史响应重采集会追加可追溯新记录而非静默覆盖(
    local_data_root: Path,
) -> None:
    """相同内容的再次采集必须产生新的原始和规范化版本，并保留各自父链。"""

    服务 = VersioningService(local_data_root)
    工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)

    首次 = 工作者.collect_and_save(**采集参数())
    第二次 = 工作者.collect_and_save(**采集参数())

    assert 首次.raw_version_id != 第二次.raw_version_id
    assert 首次.normalized_version_id != 第二次.normalized_version_id
    assert 服务.read_bytes("market-data-raw", 首次.raw_version_id) == 固定历史日线响应()
    assert (
        服务.read_bytes("market-data-raw", 第二次.raw_version_id) == 固定历史日线响应()
    )
    assert (
        服务.metadata_for("market-data-normalized", 首次.normalized_version_id)[
            "parent_version_id"
        ]
        == 首次.raw_version_id
    )
    assert (
        服务.metadata_for("market-data-normalized", 第二次.normalized_version_id)[
            "parent_version_id"
        ]
        == 第二次.raw_version_id
    )


@pytest.mark.parametrize(
    "原始响应",
    [
        b'{"bars":[{"trade_date":"2026-07-13","open":10.0,"high":10.5,"low":9.8,"close":10.2}]}',
        b'{"bars":[{"trade_date":"2026-07-13","open":10.0,"high":10.5,"low":9.8,"close":10.2,"volume":1000},{"trade_date":"2026-07-14","open":10.0,"high":9.8,"low":9.9,"close":10.2,"volume":1000}]}',
    ],
)
def test_任一日线字段非法时原始与规范化两侧均不留下半批记录(
    原始响应: bytes, local_data_root: Path
) -> None:
    """验证、解析或规范化失败都必须整批回滚，并给出明确的失败原因。"""

    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError

    服务 = VersioningService(local_data_root)
    工作者 = 创建工作者(lambda **_参数: 原始响应, 服务)

    with pytest.raises(HistoricalDailyIngestionError, match="字段|价格|日线|完整"):
        工作者.collect_and_save(**采集参数())

    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()


@pytest.mark.parametrize("失败数据集", ["market-data-raw", "market-data-normalized"])
def test_任一工件保存失败时历史日线原子回滚且报告失败原因(
    失败数据集: str, local_data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """两侧工件必须作为一个批次提交；任一保存失败均不可留下可见版本。"""

    from stock_agent.workers.market_ingestion import HistoricalDailyIngestionError

    服务 = VersioningService(local_data_root)
    原提交 = 服务.commit_bytes

    def 失败提交(*, dataset: str, **参数: object):
        if dataset == 失败数据集:
            raise OSError(f"{失败数据集} 保存失败")
        return 原提交(dataset=dataset, **参数)

    monkeypatch.setattr(服务, "commit_bytes", 失败提交)
    工作者 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务)

    with pytest.raises(HistoricalDailyIngestionError, match="保存失败"):
        工作者.collect_and_save(**采集参数())

    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()


def test_历史日线不得作为当前预测的实时输入(local_data_root: Path) -> None:
    """闭环产物只能用于历史研究；即使日线完整也必须被当前预测入口拒绝。"""

    服务 = VersioningService(local_data_root)
    结果 = 创建工作者(lambda **_参数: 固定历史日线响应(), 服务).collect_and_save(
        **采集参数()
    )

    with pytest.raises(FreshnessClassificationError, match="历史|实时|不可用|休市"):
        is_usable_for_current_prediction(结果.bars[0].model_dump(mode="python"))
