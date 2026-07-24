def test_默认注册中信与国泰海通且都不可交易() -> None:
    from bagholder.adapters.broker.registry import BrokerRegistry
    from bagholder.domain.broker import BrokerApiState, BrokerCode

    accounts = BrokerRegistry.default_accounts()

    assert {account.broker for account in accounts} == {
        BrokerCode.CITIC,
        BrokerCode.GUOTAI_HAITONG,
    }
    assert all(account.api_state is BrokerApiState.API_UNAVAILABLE for account in accounts)
    assert all(not account.capabilities.supports_live_orders for account in accounts)


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
