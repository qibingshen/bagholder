"""将已验证市场证据交给 TradingAgents 并固化研究决策。"""

from __future__ import annotations

import os
from datetime import date
from typing import Protocol
from uuid import uuid4

from bagholder.contracts.live_trading import ResearchDecision
from bagholder.contracts.market_data import (
    MarketSnapshot,
    ResearchProcessRequest,
    ResearchProcessResult,
)
from bagholder.infrastructure.sqlite_store import SqlitePlatformStore


class ResearchClient(Protocol):
    """研究服务所需的隔离客户端能力。"""

    def run_research(self, request: ResearchProcessRequest) -> ResearchProcessResult: ...


class ResearchConfigurationError(RuntimeError):
    """研究模型配置未满足安全要求。"""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class ResearchService:
    """验证证据、运行智能体研究并保存完整证据链。"""

    def __init__(self, client: ResearchClient, store: SqlitePlatformStore) -> None:
        self._client = client
        self._store = store

    def run(
        self,
        *,
        market_evidence_id: str,
        analysis_date: date,
    ) -> ResearchDecision:
        """只基于已登记市场证据产生结构化研究决策。"""

        api_key = os.getenv("TRADINGAGENTS_API_KEY", "").strip()
        model = os.getenv("TRADINGAGENTS_MODEL", "").strip()
        if not api_key or not model:
            raise ResearchConfigurationError("MODEL_NOT_CONFIGURED")

        market_record = self._store.get_evidence_record(market_evidence_id)
        if market_record.kind != "MARKET":
            raise ValueError("研究输入必须是市场证据")
        market_payload = self._store.load_evidence(market_evidence_id)
        snapshot = MarketSnapshot.model_validate(market_payload)
        if analysis_date > snapshot.as_of:
            raise ValueError("分析日期不能晚于市场证据时点")

        result = self._client.run_research(
            ResearchProcessRequest(
                symbol=snapshot.security_key.removeprefix("CN:").split(".", maxsplit=1)[0],
                security_key=snapshot.security_key,
                analysis_date=analysis_date,
                as_of=snapshot.retrieved_at,
                evidence_ids=[market_record.evidence_id],
                data_version=market_record.sha256,
                model_config_payload={"output_language": "Chinese"},
            )
        )
        research_payload: dict[str, object] = {
            "schema_version": "research-v1",
            "source": "TradingAgents-Astock",
            "security_key": snapshot.security_key,
            "analysis_date": analysis_date.isoformat(),
            "as_of": result.as_of.isoformat(),
            "market_evidence_id": market_record.evidence_id,
            "data_version": market_record.sha256,
            "action": result.action,
            "confidence": str(result.confidence),
            "model_version": result.model_version,
            "risk_flags": result.risk_flags,
            "reports": result.reports,
        }
        research_record = self._store.save_evidence(
            kind="RESEARCH",
            security_key=snapshot.security_key,
            payload=research_payload,
            created_at=result.as_of,
        )
        decision = ResearchDecision(
            decision_id=uuid4(),
            security_key=snapshot.security_key,
            as_of=result.as_of,
            action=result.action,
            confidence=result.confidence,
            evidence_ids=[market_record.evidence_id, research_record.evidence_id],
            data_version=market_record.sha256,
            model_version=result.model_version,
            risk_flags=result.risk_flags,
        )
        self._store.save_research_decision(decision)
        return decision

