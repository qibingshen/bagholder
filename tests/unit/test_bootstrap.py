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


def test_状态命令明确显示两个账户默认不可交易(capsys) -> None:
    from bagholder.bootstrap import main

    exit_code = main(["status", "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["project"] == "bagholder-trading-platform"
    assert {account["broker"] for account in output["accounts"]} == {
        "CITIC",
        "GUOTAI_HAITONG",
    }
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
