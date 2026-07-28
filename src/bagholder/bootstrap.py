"""A 股智能体交易平台命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from bagholder import __version__
from bagholder.adapters.broker.broker_runtime_registry import (
    BrokerRuntimeBinding,
)
from bagholder.application.execution_service import LiveBlockedError
from bagholder.contracts.live_trading import ExecutionMode, OrderProposal
from bagholder.domain.broker import BrokerCode
from bagholder.domain.pipeline import PipelineRun
from bagholder.runtime import PlatformRuntime, build_runtime


def _status_payload(runtime: PlatformRuntime) -> dict[str, Any]:
    return {
        "project": "bagholder-trading-platform",
        "version": __version__,
        "live_trading_enabled": runtime.system_live_enabled,
        "configuration_errors": [
            {
                "source_file": item.source_file,
                "error_code": item.error_code,
            }
            for item in runtime.broker_registry.configuration_errors()
        ],
        "accounts": [
            {
                "account_id": binding.config.account_id,
                "broker": binding.config.broker_code.value,
                "account_live_enabled": binding.account_live_enabled,
                "api_state": binding.api_state.value,
                "supports_live_orders": bool(
                    binding.health.get("live_orders", False)
                ),
                "reason": binding.reason,
            }
            for binding in runtime.broker_registry.bindings()
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bagholder")
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="查看项目和券商账户状态")
    status.add_argument("--json", action="store_true", dest="as_json")

    doctor = commands.add_parser("doctor", help="检查三个 Python 环境")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    paper = commands.add_parser("paper", help="管理模拟账户")
    paper_commands = paper.add_subparsers(dest="paper_command", required=True)
    account = paper_commands.add_parser("account")
    account_commands = account.add_subparsers(dest="account_command", required=True)
    create_account = account_commands.add_parser("create")
    create_account.add_argument("--account", required=True)
    create_account.add_argument("--cash", required=True)
    create_account.add_argument("--json", action="store_true", dest="as_json")
    show_account = account_commands.add_parser("show")
    show_account.add_argument("account")
    show_account.add_argument("--json", action="store_true", dest="as_json")

    market = commands.add_parser("market", help="获取真实 A 股行情")
    market_commands = market.add_subparsers(dest="market_command", required=True)
    fetch = market_commands.add_parser("fetch")
    fetch.add_argument("security_key")
    fetch.add_argument("--start", required=True)
    fetch.add_argument("--end", required=True)
    fetch.add_argument("--json", action="store_true", dest="as_json")

    research = commands.add_parser("research", help="运行 TradingAgents 研究")
    research_commands = research.add_subparsers(dest="research_command", required=True)
    research_run = research_commands.add_parser("run")
    research_run.add_argument("security_key")
    research_run.add_argument("--date", required=True)
    research_run.add_argument("--start")
    research_run.add_argument("--evidence-id")
    research_run.add_argument("--json", action="store_true", dest="as_json")

    pipeline = commands.add_parser("pipeline", help="运行和审批交易管道")
    pipeline_commands = pipeline.add_subparsers(dest="pipeline_command", required=True)
    pipeline_run = pipeline_commands.add_parser("run")
    pipeline_run.add_argument("security_key")
    pipeline_run.add_argument("--account", required=True)
    pipeline_run.add_argument("--date", required=True)
    pipeline_run.add_argument("--start")
    pipeline_run.add_argument(
        "--mode",
        choices=[mode.value for mode in ExecutionMode],
        default=ExecutionMode.PAPER.value,
    )
    pipeline_run.add_argument("--json", action="store_true", dest="as_json")
    pipeline_approve = pipeline_commands.add_parser("approve")
    pipeline_approve.add_argument("run_id")
    pipeline_approve.add_argument(
        "--mode",
        choices=[mode.value for mode in ExecutionMode],
        required=True,
    )
    pipeline_approve.add_argument(
        "--broker",
        choices=[item.value for item in BrokerCode],
    )
    pipeline_approve.add_argument("--confirm-live", action="store_true")
    pipeline_approve.add_argument("--json", action="store_true", dest="as_json")
    pipeline_show = pipeline_commands.add_parser("show")
    pipeline_show.add_argument("run_id")
    pipeline_show.add_argument("--json", action="store_true", dest="as_json")

    order = commands.add_parser("order", help="查询本地订单")
    order_commands = order.add_subparsers(dest="order_command", required=True)
    order_show = order_commands.add_parser("show")
    order_show.add_argument("order_id")
    order_show.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _load_project_env(project_root: Path) -> None:
    """从被 Git 忽略的项目根目录 .env 补充未设置的环境变量。"""

    env_file = project_root / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        if not key:
            continue
        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {"\"", "'"}
        ):
            normalized_value = normalized_value[1:-1]
        os.environ.setdefault(key, normalized_value)


def main(argv: Sequence[str] | None = None) -> int:
    """执行一条 CLI 命令并返回进程退出码。"""

    _load_project_env(Path.cwd())
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return _emit(_doctor_payload(), args.as_json)

    try:
        runtime = build_runtime()
        payload = (
            _status_payload(runtime)
            if args.command == "status"
            else _execute(args, runtime)
        )
    except Exception as error:
        return _emit_error(error, bool(getattr(args, "as_json", False)))
    return _emit(payload, bool(getattr(args, "as_json", False)))


def _execute(args: argparse.Namespace, runtime: PlatformRuntime) -> object:
    now = datetime.now(UTC)
    if args.command == "paper" and args.account_command == "create":
        runtime.paper.create_account(args.account, Decimal(args.cash), now)
        return runtime.store.get_paper_account(args.account)
    if args.command == "paper" and args.account_command == "show":
        return runtime.store.get_paper_account(args.account)
    if args.command == "market" and args.market_command == "fetch":
        end = date.fromisoformat(args.end)
        return runtime.market.fetch(
            security_key=args.security_key,
            start_date=date.fromisoformat(args.start),
            end_date=end,
            as_of=end,
        )
    if args.command == "research" and args.research_command == "run":
        analysis_date = date.fromisoformat(args.date)
        evidence_id = args.evidence_id
        if not evidence_id:
            start = (
                date.fromisoformat(args.start)
                if args.start
                else analysis_date - timedelta(days=30)
            )
            evidence_id = runtime.market.fetch(
                security_key=args.security_key,
                start_date=start,
                end_date=analysis_date,
                as_of=analysis_date,
            ).evidence_id
        return runtime.research.run(
            market_evidence_id=evidence_id,
            analysis_date=analysis_date,
        )
    if args.command == "pipeline" and args.pipeline_command == "run":
        analysis_date = date.fromisoformat(args.date)
        start = (
            date.fromisoformat(args.start)
            if args.start
            else analysis_date - timedelta(days=30)
        )
        mode = ExecutionMode(args.mode)
        context = (
            runtime.paper_risk_context(args.account, args.security_key)
            if mode is ExecutionMode.PAPER
            else runtime.live_risk_context(args.account, args.security_key)
        )
        return runtime.pipeline.run(
            security_key=args.security_key,
            account_id=args.account,
            analysis_date=analysis_date,
            start_date=start,
            mode=mode,
            risk_context=context,
            now=now,
        )
    if args.command == "pipeline" and args.pipeline_command == "approve":
        mode = ExecutionMode(args.mode)
        _validate_broker_argument(mode, args.broker)
        run = runtime.pipeline.show(args.run_id)
        confirmed = False
        live_context = None
        if mode is ExecutionMode.LIVE:
            binding = runtime.broker_binding(run.account_id)
            _validate_live_broker(str(args.broker), binding)
            confirmed = _confirm_live(
                args.confirm_live,
                runtime,
                run,
                binding.config.broker_code,
            )
            live_context = runtime.live_gate_context(
                run.account_id,
                interactive_confirmation=confirmed,
            )
        return runtime.pipeline.approve(
            run_id=args.run_id,
            mode=mode,
            interactive_confirmation=confirmed,
            live_context=live_context,
            now=now,
        )
    if args.command == "pipeline" and args.pipeline_command == "show":
        return runtime.pipeline.show(args.run_id)
    if args.command == "order" and args.order_command == "show":
        return runtime.store.get_order(args.order_id)
    raise ValueError("不支持的命令")


def _validate_broker_argument(
    mode: ExecutionMode,
    requested_broker: str | None,
) -> None:
    if mode is ExecutionMode.PAPER and requested_broker is not None:
        raise LiveBlockedError("BROKER_NOT_ALLOWED_FOR_PAPER")
    if mode is ExecutionMode.LIVE and requested_broker is None:
        raise LiveBlockedError("BROKER_CONFIRMATION_REQUIRED")


def _validate_live_broker(
    requested_broker: str,
    binding: BrokerRuntimeBinding,
) -> None:
    if requested_broker != binding.config.broker_code.value:
        raise LiveBlockedError("BROKER_ACCOUNT_MISMATCH")


def _live_confirmation_text(
    broker_code: BrokerCode,
    proposal: OrderProposal,
) -> str:
    return (
        f"{broker_code.value} {proposal.account_id} "
        f"{proposal.security_key} {proposal.side.value} {proposal.quantity}"
    )


def _confirm_live(
    requested: bool,
    runtime: PlatformRuntime,
    run: PipelineRun,
    broker_code: BrokerCode,
) -> bool:
    if not requested or not sys.stdin.isatty():
        raise LiveBlockedError("LIVE_CONFIRMATION_REQUIRED")
    run_id = run.run_id
    proposal_id = run.proposal_id
    if not isinstance(proposal_id, str):
        raise RuntimeError("管道缺少订单提案")
    proposal = OrderProposal.model_validate(runtime.store.get_order_proposal(proposal_id))
    expected = _live_confirmation_text(broker_code, proposal)
    entered = input(f"请输入以下内容确认实盘订单：{expected}\n> ").strip()
    if entered != expected:
        raise LiveBlockedError("LIVE_CONFIRMATION_REQUIRED")
    return bool(run_id)


def _doctor_payload() -> dict[str, object]:
    root = Path.cwd()
    trading_python = Path(
        os.getenv(
            "TRADINGAGENTS_PYTHON",
            root / ".runtime" / "tradingagents" / "Scripts" / "python.exe",
        )
    )
    vnpy_python = Path(
        os.getenv(
            "BAGHOLDER_VNPY_PYTHON",
            root / ".runtime" / "vnpy" / "Scripts" / "python.exe",
        )
    )
    return {
        "main": {"ready": True, "version": __version__},
        "tradingagents": _python_import_check(
            trading_python,
            "from tradingagents.graph.trading_graph import TradingAgentsGraph",
        ),
        "vnpy": _python_import_check(vnpy_python, "import vnpy"),
    }


def _python_import_check(executable: Path, statement: str) -> dict[str, object]:
    if not executable.exists():
        return {"ready": False, "reason": "PYTHON_NOT_FOUND"}
    try:
        result = subprocess.run(
            [str(executable), "-c", statement],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ready": False, "reason": "IMPORT_CHECK_FAILED"}
    return {
        "ready": result.returncode == 0,
        "reason": None if result.returncode == 0 else "IMPORT_FAILED",
    }


def _emit(payload: object, as_json: bool) -> int:
    normalized = _jsonable(payload)
    if as_json:
        print(json.dumps(normalized, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(normalized, ensure_ascii=False, indent=2))
    return 0


def _emit_error(error: Exception, as_json: bool) -> int:
    error_code = getattr(error, "error_code", type(error).__name__)
    payload = {"ok": False, "error_code": str(error_code)}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"操作失败：{error_code}", file=sys.stderr)
    return 1


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


if __name__ == "__main__":
    raise SystemExit(main())
