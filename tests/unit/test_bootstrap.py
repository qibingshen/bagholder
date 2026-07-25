import json
import sys
from pathlib import Path


def _fake_runner(tmp_path: Path) -> Path:
    runner = tmp_path / "fake_tradingagents_runner.py"
    runner.write_text(
        """
import json
import sys

request = json.loads(sys.stdin.readline())
operation = request["operation"]
payload = request["payload"]
if operation == "FETCH_MARKET":
    result = {
        "security_key": payload["security_key"],
        "start_date": payload["start_date"],
        "end_date": payload["end_date"],
        "as_of": payload["as_of"],
        "retrieved_at": "2026-07-25T03:00:00+00:00",
        "source": "controlled CLI fixture",
        "records": [{
            "date": payload["end_date"],
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100",
            "volume": 100000
        }],
        "schema_version": "market-v1"
    }
elif operation == "RUN_RESEARCH":
    result = {
        "action": "BUY",
        "confidence": "0.80",
        "model_version": "controlled-cli-model",
        "as_of": "2026-07-25T03:00:00+00:00",
        "risk_flags": [],
        "reports": {"market_report": "controlled"}
    }
else:
    print(json.dumps({"ok": False, "error_code": "UNKNOWN"}))
    raise SystemExit(0)
print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
""".lstrip(),
        encoding="utf-8",
    )
    return runner


def _configure_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BAGHOLDER_HOME", str(tmp_path / "runtime"))
    monkeypatch.setenv("TRADINGAGENTS_PYTHON", sys.executable)
    monkeypatch.setenv("TRADINGAGENTS_RUNNER", str(_fake_runner(tmp_path)))
    monkeypatch.setenv("TRADINGAGENTS_API_KEY", "test-key")
    monkeypatch.setenv("TRADINGAGENTS_MODEL", "test-model")


def _write_broker_configs(tmp_path: Path) -> Path:
    directory = tmp_path / "brokers"
    directory.mkdir()
    capabilities = [
        "live_orders",
        "cancel",
        "funds_query",
        "positions_query",
        "orders_query",
        "trades_query",
        "market_data",
    ]
    profiles = (
        (
            "citic.json",
            "citic-main",
            "CITIC",
            "BAGHOLDER_CITIC_MAIN",
        ),
        (
            "guotai.json",
            "guotai-haitong-main",
            "GUOTAI_HAITONG",
            "BAGHOLDER_GUOTAI_HAITONG_MAIN",
        ),
    )
    for filename, account_id, broker, prefix in profiles:
        (directory / filename).write_text(
            json.dumps(
                {
                    "account_id": account_id,
                    "broker_code": broker,
                    "display_name": broker,
                    "currency": "CNY",
                    "environment_prefix": prefix,
                    "required_capabilities": capabilities,
                }
            ),
            encoding="utf-8",
        )
    return directory


def test_status_显示真实总开关和账户开关(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from bagholder.bootstrap import main

    config_dir = _write_broker_configs(tmp_path)
    monkeypatch.setenv("BAGHOLDER_BROKER_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("BAGHOLDER_HOME", str(tmp_path / "runtime"))
    monkeypatch.setenv("BAGHOLDER_LIVE_ENABLED", "true")
    monkeypatch.setenv("BAGHOLDER_CITIC_MAIN_LIVE_ENABLED", "true")

    exit_code = main(["status", "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["live_trading_enabled"] is True
    accounts = {item["account_id"]: item for item in output["accounts"]}
    assert accounts["citic-main"]["account_live_enabled"] is True
    assert accounts["guotai-haitong-main"]["account_live_enabled"] is False
    assert all(account["api_state"] == "API_UNAVAILABLE" for account in output["accounts"])


def test_market_fetch_json_输出证据版本(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from bagholder.bootstrap import main

    _configure_runtime(monkeypatch, tmp_path)

    exit_code = main(
        [
            "market",
            "fetch",
            "CN:600519.SH",
            "--start",
            "2026-07-24",
            "--end",
            "2026-07-24",
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["security_key"] == "CN:600519.SH"
    assert len(output["sha256"]) == 64
    assert output["source"] == "controlled CLI fixture"


def test_cli_可以创建账户运行审批并模拟成交(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from bagholder.bootstrap import main

    _configure_runtime(monkeypatch, tmp_path)
    assert (
        main(
            [
                "paper",
                "account",
                "create",
                "--account",
                "paper-main",
                "--cash",
                "1000000",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "pipeline",
                "run",
                "CN:600519.SH",
                "--account",
                "paper-main",
                "--date",
                "2026-07-24",
                "--start",
                "2026-07-24",
                "--mode",
                "PAPER",
                "--json",
            ]
        )
        == 0
    )
    waiting = json.loads(capsys.readouterr().out)
    assert waiting["state"] == "WAITING_APPROVAL"

    assert (
        main(
            [
                "pipeline",
                "approve",
                waiting["run_id"],
                "--mode",
                "PAPER",
                "--json",
            ]
        )
        == 0
    )
    completed = json.loads(capsys.readouterr().out)
    assert completed["state"] == "RECONCILED"
    assert completed["order_id"].startswith("PAPER-")


def test_live_审批缺少券商时先于运行查询被拒绝(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from bagholder.bootstrap import main

    _configure_runtime(monkeypatch, tmp_path)
    exit_code = main(
        [
            "pipeline",
            "approve",
            "nonexistent-run",
            "--mode",
            "LIVE",
            "--confirm-live",
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error_code"] == "BROKER_CONFIRMATION_REQUIRED"


def test_paper_审批携带券商时先于运行查询被拒绝(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from bagholder.bootstrap import main

    _configure_runtime(monkeypatch, tmp_path)
    exit_code = main(
        [
            "pipeline",
            "approve",
            "nonexistent-run",
            "--mode",
            "PAPER",
            "--broker",
            "CITIC",
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error_code"] == "BROKER_NOT_ALLOWED_FOR_PAPER"


def test_live_审批券商必须匹配运行账户() -> None:
    import pytest

    from bagholder.adapters.broker.broker_config import BrokerAccountConfig
    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeBinding,
    )
    from bagholder.application.execution_service import LiveBlockedError
    from bagholder.bootstrap import _validate_live_broker
    from bagholder.domain.broker import BrokerApiState, BrokerCode

    binding = BrokerRuntimeBinding(
        BrokerAccountConfig(
            "citic-main",
            BrokerCode.CITIC,
            "中信证券",
            "CNY",
            "BAGHOLDER_CITIC_MAIN",
            frozenset({"live_orders"}),
        ),
        False,
        None,
        BrokerApiState.API_UNAVAILABLE,
        {},
        "GATEWAY_CONFIG_INCOMPLETE",
    )

    with pytest.raises(LiveBlockedError) as captured:
        _validate_live_broker("GUOTAI_HAITONG", binding)

    assert captured.value.error_code == "BROKER_ACCOUNT_MISMATCH"


def test_live_确认文本包含券商账户证券方向和数量() -> None:
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal
    from uuid import uuid4

    from bagholder.bootstrap import _live_confirmation_text
    from bagholder.contracts.live_trading import (
        ExecutionMode,
        OrderProposal,
        OrderSide,
    )
    from bagholder.domain.broker import BrokerCode

    now = datetime(2026, 7, 25, 6, tzinfo=UTC)
    proposal = OrderProposal(
        proposal_id=uuid4(),
        decision_id=uuid4(),
        account_id="citic-main",
        security_key="CN:600000.SH",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10"),
        mode=ExecutionMode.LIVE,
        created_at=now,
        expires_at=now + timedelta(minutes=2),
    )

    assert _live_confirmation_text(BrokerCode.CITIC, proposal) == (
        "CITIC citic-main CN:600000.SH BUY 100"
    )


def test_status_不输出账户插件摘要或密钥(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from bagholder.bootstrap import main

    config_dir = _write_broker_configs(tmp_path)
    monkeypatch.setenv("BAGHOLDER_BROKER_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("BAGHOLDER_HOME", str(tmp_path / "runtime"))
    monkeypatch.setenv(
        "BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN",
        "bagholder_vnpy_private:create_gateway",
    )
    monkeypatch.setenv("BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256", "f" * 64)
    monkeypatch.setenv(
        "BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX",
        "super-secret-node-value",
    )

    assert main(["status", "--json"]) == 0
    rendered = capsys.readouterr().out

    assert "super-secret-node-value" not in rendered
    assert "bagholder_vnpy_private:create_gateway" not in rendered
    assert "f" * 64 not in rendered
