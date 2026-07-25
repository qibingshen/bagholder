from pathlib import Path


def test_仓库默认券商配置可被统一加载() -> None:
    from bagholder.adapters.broker.broker_config import BrokerConfigLoader
    from bagholder.domain.broker import BrokerCode

    root = Path(__file__).parents[2]
    result = BrokerConfigLoader().load(root / "config" / "brokers")

    assert result.errors == ()
    assert {
        (item.account_id, item.broker_code, item.environment_prefix)
        for item in result.accounts
    } == {
        ("citic-main", BrokerCode.CITIC, "BAGHOLDER_CITIC_MAIN"),
        (
            "guotai-haitong-main",
            BrokerCode.GUOTAI_HAITONG,
            "BAGHOLDER_GUOTAI_HAITONG_MAIN",
        ),
    }


def test_没有受信插件不能绑定为可交易账户() -> None:
    from bagholder.adapters.broker.registry import BrokerRegistry
    from bagholder.domain.broker import BrokerCode

    registry = BrokerRegistry([])

    try:
        registry.bind(BrokerCode.CITIC)
    except LookupError as error:
        assert "受信 Gateway" in str(error)
    else:
        raise AssertionError("没有受信 Gateway 时必须拒绝绑定")
