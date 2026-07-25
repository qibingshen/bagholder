import json
from pathlib import Path


def _write_config(directory: Path, name: str, payload: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _valid(
    account_id: str = "citic-main",
    broker_code: str = "CITIC",
    prefix: str = "BAGHOLDER_CITIC_MAIN",
) -> dict[str, object]:
    return {
        "account_id": account_id,
        "broker_code": broker_code,
        "display_name": "测试券商",
        "currency": "CNY",
        "environment_prefix": prefix,
        "required_capabilities": [
            "live_orders",
            "cancel",
            "funds_query",
            "positions_query",
            "orders_query",
            "trades_query",
            "market_data",
        ],
    }


def test_按文件名稳定加载两个券商账户(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_config import BrokerConfigLoader
    from bagholder.domain.broker import BrokerCode

    _write_config(
        tmp_path,
        "02-guotai.json",
        _valid(
            "guotai-haitong-main",
            "GUOTAI_HAITONG",
            "BAGHOLDER_GUOTAI_HAITONG_MAIN",
        ),
    )
    _write_config(tmp_path, "01-citic.json", _valid())

    result = BrokerConfigLoader().load(tmp_path)

    assert result.errors == ()
    assert [item.account_id for item in result.accounts] == [
        "citic-main",
        "guotai-haitong-main",
    ]
    assert result.accounts[0].broker_code is BrokerCode.CITIC


def test_单个非法文件不阻止其他账户(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_config import BrokerConfigLoader

    _write_config(tmp_path, "citic.json", _valid())
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")

    result = BrokerConfigLoader().load(tmp_path)

    assert [item.account_id for item in result.accounts] == ["citic-main"]
    assert [(item.source_file, item.error_code) for item in result.errors] == [
        ("broken.json", "BROKER_CONFIG_INVALID")
    ]


def test_重复账户使两个冲突配置都失效(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_config import BrokerConfigLoader

    _write_config(tmp_path, "one.json", _valid(prefix="BAGHOLDER_ONE"))
    _write_config(tmp_path, "two.json", _valid(prefix="BAGHOLDER_TWO"))

    result = BrokerConfigLoader().load(tmp_path)

    assert result.accounts == ()
    assert {item.error_code for item in result.errors} == {
        "DUPLICATE_ACCOUNT_CONFIG"
    }


def test_未知能力和非法环境前缀被拒绝(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_config import BrokerConfigLoader

    invalid = _valid(prefix="citic-main")
    invalid["required_capabilities"] = ["live_orders", "unknown"]
    _write_config(tmp_path, "invalid.json", invalid)

    result = BrokerConfigLoader().load(tmp_path)

    assert result.accounts == ()
    assert result.errors[0].error_code == "BROKER_CONFIG_INVALID"


def test_目录不存在时返回脱敏错误(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_config import (
        BrokerConfigLoader,
        BrokerConfigurationError,
    )

    missing = tmp_path / "missing-brokers"

    result = BrokerConfigLoader().load(missing)

    assert result.accounts == ()
    assert result.errors == (
        BrokerConfigurationError(
            source_file="missing-brokers",
            error_code="CONFIG_DIRECTORY_MISSING",
        ),
    )
