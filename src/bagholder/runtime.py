"""命令行平台的依赖装配与本地运行状态。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from bagholder.adapters.broker.broker_config import BrokerConfigLoader
from bagholder.adapters.broker.broker_runtime_registry import (
    BrokerRuntimeBinding,
    BrokerRuntimeRegistry,
)
from bagholder.application.approval_service import ApprovalService
from bagholder.application.execution_service import (
    AccountRoutedLiveExecutionService,
    ExecutionRouter,
    LiveBlockedError,
    LiveGateContext,
)
from bagholder.application.market_data_service import MarketDataService
from bagholder.application.paper_execution_service import PaperExecutionService
from bagholder.application.pipeline_service import PipelineService
from bagholder.application.research_service import ResearchService
from bagholder.application.risk_service import LiveRiskService
from bagholder.application.signal_to_order import SignalToOrderService
from bagholder.domain.broker import (
    BrokerApiState,
)
from bagholder.domain.risk import LiveRiskContext
from bagholder.infrastructure.sqlite_store import SqlitePlatformStore
from bagholder.integrations.tradingagents_client import TradingAgentsClient


@dataclass(frozen=True, slots=True)
class PlatformRuntime:
    """CLI 每次调用所需的完整本地依赖。"""

    home: Path
    store: SqlitePlatformStore
    market: MarketDataService
    research: ResearchService
    paper: PaperExecutionService
    pipeline: PipelineService
    broker_registry: BrokerRuntimeRegistry
    system_live_enabled: bool

    def broker_binding(self, account_id: str) -> BrokerRuntimeBinding:
        """返回指定账户唯一的运行时绑定。"""

        try:
            return self.broker_registry.get(account_id)
        except LookupError as error:
            raise LiveBlockedError("BROKER_ACCOUNT_NOT_FOUND") from error

    def live_gate_context(
        self,
        account_id: str,
        *,
        interactive_confirmation: bool,
    ) -> LiveGateContext:
        """根据 Gateway 健康和本地开关生成实盘门事实。"""

        binding = self.broker_binding(account_id)
        return LiveGateContext(
            system_live_enabled=self.system_live_enabled,
            account_live_enabled=binding.account_live_enabled,
            broker_api_state=binding.api_state,
            supports_live_orders=bool(binding.health.get("live_orders", False)),
            reconciled=bool(binding.health.get("reconciled", False)),
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

        binding = self.broker_binding(account_id)
        gateway = binding.gateway
        health = binding.health
        if gateway is None or binding.api_state is not BrokerApiState.READY:
            raise LiveBlockedError("BROKER_API_UNAVAILABLE")
        if not bool(health.get("market_data_ready", False)):
            raise LiveBlockedError("BROKER_MARKET_DATA_UNAVAILABLE")
        funds = gateway.query_funds(account_id)
        positions = gateway.query_positions(account_id)
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
                str(health.get("quote_age_seconds", "999"))
            ),
            reconciled=bool(health.get("reconciled", False)),
            halted=False,
            security_tradable=bool(health.get("security_tradable", False)),
            price_within_limit=bool(health.get("price_within_limit", False)),
            cash_available=cash,
            available_to_sell=available_to_sell,
            net_asset=net_asset,
            current_total_exposure=total_market_value / net_asset,
            current_security_exposure=security_market_value / net_asset,
            current_industry_exposure=Decimal(
                str(health.get("industry_exposure", "0"))
            ),
            daily_turnover=Decimal(
                str(health.get("daily_turnover", "0"))
            ),
            daily_pnl=Decimal(str(health.get("daily_pnl", "0"))),
            peak_drawdown=Decimal(
                str(health.get("peak_drawdown", "0"))
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
        timeout_seconds=_tradingagents_timeout_seconds(),
    )
    market = MarketDataService(research_client, store)
    research = ResearchService(research_client, store)
    paper = PaperExecutionService(store)

    config_dir = Path(
        os.getenv(
            "BAGHOLDER_BROKER_CONFIG_DIR",
            str(root / "config" / "brokers"),
        )
    ).resolve()
    configuration = BrokerConfigLoader().load(config_dir)
    registry = BrokerRuntimeRegistry.build(
        configuration=configuration,
        root=root,
        home=home,
    )
    live_executor = AccountRoutedLiveExecutionService(store, registry)
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
        broker_registry=registry,
        system_live_enabled=_env_true("BAGHOLDER_LIVE_ENABLED"),
    )


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _tradingagents_timeout_seconds() -> float:
    """允许长时间多智能体研究覆盖默认子进程超时。"""

    value = os.getenv("TRADINGAGENTS_TIMEOUT_SECONDS", "120").strip()
    try:
        timeout = float(value)
    except ValueError:
        return 120
    return timeout if timeout > 0 else 120
