"""命令行平台的依赖装配与本地运行状态。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from bagholder.adapters.broker.vnpy_gateway import VnpyBrokerGateway
from bagholder.application.approval_service import ApprovalService
from bagholder.application.execution_service import (
    ExecutionRouter,
    LiveBlockedError,
    LiveExecutionService,
    LiveGateContext,
)
from bagholder.application.market_data_service import MarketDataService
from bagholder.application.paper_execution_service import PaperExecutionService
from bagholder.application.pipeline_service import PipelineService
from bagholder.application.research_service import ResearchService
from bagholder.application.risk_service import LiveRiskService
from bagholder.application.signal_to_order import SignalToOrderService
from bagholder.contracts.live_trading import ExecutionRequest
from bagholder.domain.broker import (
    BrokerApiState,
    BrokerGateway,
    BrokerOrderReceipt,
)
from bagholder.domain.risk import LiveRiskContext
from bagholder.infrastructure.sqlite_store import SqlitePlatformStore
from bagholder.integrations.tradingagents_client import TradingAgentsClient
from bagholder.integrations.vnpy_client import SubprocessVnpyTransport, VnpyClient


class UnavailableLiveExecutor:
    """没有受信私有 Gateway 时的关闭默认实现。"""

    def submit(
        self,
        request: ExecutionRequest,
        now: datetime,
    ) -> BrokerOrderReceipt:
        del request, now
        raise LiveBlockedError("BROKER_API_UNAVAILABLE")


@dataclass(frozen=True, slots=True)
class PlatformRuntime:
    """CLI 每次调用所需的完整本地依赖。"""

    home: Path
    store: SqlitePlatformStore
    market: MarketDataService
    research: ResearchService
    paper: PaperExecutionService
    pipeline: PipelineService
    live_gateway: BrokerGateway | None
    live_api_state: BrokerApiState
    live_health: dict[str, object]
    system_live_enabled: bool
    account_live_enabled: bool

    def live_gate_context(
        self,
        *,
        interactive_confirmation: bool,
    ) -> LiveGateContext:
        """根据 Gateway 健康和本地开关生成实盘门事实。"""

        return LiveGateContext(
            system_live_enabled=self.system_live_enabled,
            account_live_enabled=self.account_live_enabled,
            broker_api_state=self.live_api_state,
            supports_live_orders=bool(self.live_health.get("live_orders", False)),
            reconciled=bool(self.live_health.get("reconciled", False)),
            interactive_confirmation=interactive_confirmation,
        )

    def paper_risk_context(
        self,
        account_id: str,
        security_key: str,
    ) -> LiveRiskContext:
        """从模拟账本生成确定性风控事实。"""

        account = self.store.get_paper_account(account_id)
        positions = self.store.list_paper_positions(account_id)
        total_market_value = sum(
            (
                position.average_cost * position.total_quantity
                for position in positions
            ),
            start=Decimal("0"),
        )
        security_position = next(
            (item for item in positions if item.security_key == security_key),
            None,
        )
        security_value = (
            security_position.average_cost * security_position.total_quantity
            if security_position is not None
            else Decimal("0")
        )
        net_asset = account.cash + total_market_value
        if net_asset <= 0:
            raise ValueError("模拟账户净资产必须大于零")
        security_exposure = security_value / net_asset
        return LiveRiskContext(
            quote_age_seconds=Decimal("0"),
            reconciled=True,
            halted=account.status != "ACTIVE",
            security_tradable=True,
            price_within_limit=True,
            cash_available=account.cash,
            available_to_sell=(
                security_position.available_to_sell
                if security_position is not None
                else 0
            ),
            net_asset=net_asset,
            current_total_exposure=total_market_value / net_asset,
            current_security_exposure=security_exposure,
            current_industry_exposure=security_exposure,
            daily_turnover=Decimal("0"),
            daily_pnl=Decimal("0"),
            peak_drawdown=Decimal("0"),
        )

    def live_risk_context(
        self,
        account_id: str,
        security_key: str,
    ) -> LiveRiskContext:
        """从就绪的私有 Gateway 查询真实账户风控事实。"""

        if self.live_gateway is None or self.live_api_state is not BrokerApiState.READY:
            raise LiveBlockedError("BROKER_API_UNAVAILABLE")
        if not bool(self.live_health.get("market_data_ready", False)):
            raise LiveBlockedError("BROKER_MARKET_DATA_UNAVAILABLE")
        funds = self.live_gateway.query_funds(account_id)
        positions = self.live_gateway.query_positions(account_id)
        net_asset = funds["net_asset"]
        cash = funds["cash_available"]
        total_market_value = Decimal("0")
        security_market_value = Decimal("0")
        available_to_sell = 0
        for position in positions:
            market_value = Decimal(str(position.get("market_value", "0")))
            total_market_value += market_value
            if position.get("security_key") == security_key:
                security_market_value = market_value
                available_to_sell = int(str(position.get("available_to_sell", 0)))
        return LiveRiskContext(
            quote_age_seconds=Decimal(
                str(self.live_health.get("quote_age_seconds", "999"))
            ),
            reconciled=bool(self.live_health.get("reconciled", False)),
            halted=False,
            security_tradable=bool(
                self.live_health.get("security_tradable", False)
            ),
            price_within_limit=bool(
                self.live_health.get("price_within_limit", False)
            ),
            cash_available=cash,
            available_to_sell=available_to_sell,
            net_asset=net_asset,
            current_total_exposure=total_market_value / net_asset,
            current_security_exposure=security_market_value / net_asset,
            current_industry_exposure=Decimal(
                str(self.live_health.get("industry_exposure", "0"))
            ),
            daily_turnover=Decimal(
                str(self.live_health.get("daily_turnover", "0"))
            ),
            daily_pnl=Decimal(str(self.live_health.get("daily_pnl", "0"))),
            peak_drawdown=Decimal(
                str(self.live_health.get("peak_drawdown", "0"))
            ),
        )


def build_runtime() -> PlatformRuntime:
    """从专用环境变量装配一次 CLI 运行。"""

    root = Path.cwd()
    home = Path(os.getenv("BAGHOLDER_HOME", str(root / "var"))).resolve()
    store = SqlitePlatformStore(home / "platform.db", home / "evidence")
    tradingagents_python = Path(
        os.getenv(
            "TRADINGAGENTS_PYTHON",
            str(root / ".runtime" / "tradingagents" / "Scripts" / "python.exe"),
        )
    )
    tradingagents_runner = Path(
        os.getenv(
            "TRADINGAGENTS_RUNNER",
            str(root / "integrations" / "tradingagents" / "runner.py"),
        )
    )
    research_client = TradingAgentsClient(
        python_executable=tradingagents_python,
        runner_path=tradingagents_runner,
    )
    market = MarketDataService(research_client, store)
    research = ResearchService(research_client, store)
    paper = PaperExecutionService(store)

    gateway, api_state, health = _build_live_gateway(root)
    live_executor = (
        LiveExecutionService(store, gateway)
        if gateway is not None and api_state is BrokerApiState.READY
        else UnavailableLiveExecutor()
    )
    pipeline = PipelineService(
        store=store,
        market_service=market,
        research_service=research,
        signal_service=SignalToOrderService(),
        risk_service=LiveRiskService(),
        approval_service=ApprovalService(),
        execution_router=ExecutionRouter(paper=paper, live=live_executor),
    )
    return PlatformRuntime(
        home=home,
        store=store,
        market=market,
        research=research,
        paper=paper,
        pipeline=pipeline,
        live_gateway=gateway,
        live_api_state=api_state,
        live_health=health,
        system_live_enabled=_env_true("BAGHOLDER_LIVE_ENABLED"),
        account_live_enabled=_env_true("BAGHOLDER_ACCOUNT_LIVE_ENABLED"),
    )


def _build_live_gateway(
    root: Path,
) -> tuple[BrokerGateway | None, BrokerApiState, dict[str, object]]:
    plugin = os.getenv("BAGHOLDER_VNPY_GATEWAY_PLUGIN", "").strip()
    secret_hex = os.getenv("BAGHOLDER_TRADING_NODE_SECRET_HEX", "").strip()
    if not plugin or not secret_hex:
        return None, BrokerApiState.API_UNAVAILABLE, {}
    try:
        secret = bytes.fromhex(secret_hex)
    except ValueError:
        return None, BrokerApiState.API_UNAVAILABLE, {}
    if len(secret) < 32:
        return None, BrokerApiState.API_UNAVAILABLE, {}
    transport = SubprocessVnpyTransport(
        python_executable=os.getenv(
            "BAGHOLDER_VNPY_PYTHON",
            str(root / ".runtime" / "vnpy" / "Scripts" / "python.exe"),
        ),
        server_path=root / "integrations" / "vnpy" / "server.py",
        gateway_plugin=plugin,
        secret=secret,
    )
    gateway = VnpyBrokerGateway(VnpyClient(secret=secret, transport=transport))
    try:
        health = gateway.health()
    except Exception:
        return None, BrokerApiState.DISCONNECTED, {}
    ready = (
        health.get("status") == "READY"
        and health.get("live_orders") is True
        and health.get("test_plugin") is not True
    )
    return (
        gateway,
        BrokerApiState.READY if ready else BrokerApiState.API_UNAVAILABLE,
        health,
    )


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}
