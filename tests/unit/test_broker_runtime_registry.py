import hashlib
import json
import sys
from pathlib import Path


class StubGateway:
    def __init__(self, health: dict[str, object]) -> None:
        self._health = health

    def health(self) -> dict[str, object]:
        return self._health


def _configuration(tmp_path: Path):
    from bagholder.adapters.broker.broker_config import BrokerConfigLoader

    payloads = (
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
    capabilities = [
        "live_orders",
        "cancel",
        "funds_query",
        "positions_query",
        "orders_query",
        "trades_query",
        "market_data",
    ]
    for filename, account_id, broker, prefix in payloads:
        (tmp_path / filename).write_text(
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
    return BrokerConfigLoader().load(tmp_path)


def test_两个账户独立构建状态(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeRegistry,
    )
    from bagholder.domain.broker import BrokerApiState

    configuration = _configuration(tmp_path)
    environment = {
        "BAGHOLDER_CITIC_MAIN_LIVE_ENABLED": "true",
        "BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN": "citic-plugin",
        "BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256": "a" * 64,
        "BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX": "01" * 32,
    }

    def builder(config, settings, root, home):
        del settings, root, home
        if config.account_id == "citic-main":
            return StubGateway(
                {
                    "status": "READY",
                    "broker_code": "CITIC",
                    "account_ids": ["citic-main"],
                    "live_orders": True,
                    "capabilities": list(config.required_capabilities),
                    "reconciled": True,
                    "test_plugin": False,
                }
            )
        raise AssertionError("未配置账户不能调用 Gateway builder")

    registry = BrokerRuntimeRegistry.build(
        configuration=configuration,
        root=tmp_path,
        home=tmp_path / "home",
        environment=environment,
        gateway_builder=builder,
    )

    assert registry.get("citic-main").api_state is BrokerApiState.READY
    assert registry.get("citic-main").account_live_enabled is True
    unavailable = registry.get("guotai-haitong-main")
    assert unavailable.api_state is BrokerApiState.API_UNAVAILABLE
    assert unavailable.account_live_enabled is False
    assert unavailable.reason == "GATEWAY_CONFIG_INCOMPLETE"


def _complete_environment() -> dict[str, str]:
    return {
        "BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN": "citic-plugin",
        "BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256": "a" * 64,
        "BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX": "01" * 32,
        "BAGHOLDER_GUOTAI_HAITONG_MAIN_GATEWAY_PLUGIN": "guotai-plugin",
        "BAGHOLDER_GUOTAI_HAITONG_MAIN_GATEWAY_SHA256": "b" * 64,
        "BAGHOLDER_GUOTAI_HAITONG_MAIN_TRADING_NODE_SECRET_HEX": "02" * 32,
    }


def test_身份不匹配与测试插件都不能进入_ready(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeRegistry,
    )
    from bagholder.domain.broker import BrokerApiState

    def builder(config, settings, root, home):
        del settings, root, home
        if config.account_id == "citic-main":
            return StubGateway(
                {
                    "status": "READY",
                    "broker_code": "GUOTAI_HAITONG",
                    "account_ids": ["citic-main"],
                    "live_orders": True,
                    "capabilities": list(config.required_capabilities),
                    "reconciled": True,
                    "test_plugin": False,
                }
            )
        return StubGateway(
            {
                "status": "READY",
                "broker_code": "GUOTAI_HAITONG",
                "account_ids": ["guotai-haitong-main"],
                "live_orders": True,
                "capabilities": list(config.required_capabilities),
                "reconciled": True,
                "test_plugin": True,
            }
        )

    registry = BrokerRuntimeRegistry.build(
        configuration=_configuration(tmp_path),
        root=tmp_path,
        home=tmp_path / "home",
        environment=_complete_environment(),
        gateway_builder=builder,
    )

    citic = registry.get("citic-main")
    guotai = registry.get("guotai-haitong-main")
    assert citic.api_state is BrokerApiState.API_UNAVAILABLE
    assert citic.reason == "GATEWAY_IDENTITY_MISMATCH"
    assert guotai.api_state is BrokerApiState.API_UNAVAILABLE
    assert guotai.reason == "TEST_GATEWAY_REJECTED"
    assert citic.gateway is None
    assert guotai.gateway is None


def test_一个健康检查失败不影响另一个账户(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeRegistry,
    )
    from bagholder.domain.broker import BrokerApiState

    def builder(config, settings, root, home):
        del settings, root, home
        if config.account_id == "citic-main":
            raise ConnectionError("private detail must not escape")
        return StubGateway(
            {
                "status": "READY",
                "broker_code": "GUOTAI_HAITONG",
                "account_ids": ["guotai-haitong-main"],
                "live_orders": True,
                "capabilities": list(config.required_capabilities),
                "reconciled": True,
                "test_plugin": False,
            }
        )

    registry = BrokerRuntimeRegistry.build(
        configuration=_configuration(tmp_path),
        root=tmp_path,
        home=tmp_path / "home",
        environment=_complete_environment(),
        gateway_builder=builder,
    )

    assert registry.get("citic-main").api_state is BrokerApiState.DISCONNECTED
    assert registry.get("citic-main").reason == "GATEWAY_HEALTH_FAILED"
    assert (
        registry.get("guotai-haitong-main").api_state
        is BrokerApiState.READY
    )


def test_缺少必需能力时账户不可用(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeRegistry,
    )

    def builder(config, settings, root, home):
        del settings, root, home
        capabilities = set(config.required_capabilities)
        capabilities.remove("cancel")
        return StubGateway(
            {
                "status": "READY",
                "broker_code": config.broker_code.value,
                "account_ids": [config.account_id],
                "live_orders": True,
                "capabilities": sorted(capabilities),
                "reconciled": True,
                "test_plugin": False,
            }
        )

    registry = BrokerRuntimeRegistry.build(
        configuration=_configuration(tmp_path),
        root=tmp_path,
        home=tmp_path / "home",
        environment=_complete_environment(),
        gateway_builder=builder,
    )

    assert registry.get("citic-main").reason == "GATEWAY_CAPABILITY_MISSING"
    assert (
        registry.get("guotai-haitong-main").reason
        == "GATEWAY_CAPABILITY_MISSING"
    )


def test_默认构建器加载签名节点但拒绝测试_gateway(tmp_path: Path) -> None:
    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeRegistry,
    )
    from bagholder.domain.broker import BrokerApiState

    root = Path(__file__).parents[2]
    plugin_path = root / "integrations" / "vnpy" / "bagholder_vnpy_fake.py"
    environment = {
        "BAGHOLDER_CITIC_MAIN_LIVE_ENABLED": "true",
        "BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN": (
            "bagholder_vnpy_fake:create_gateway"
        ),
        "BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256": hashlib.sha256(
            plugin_path.read_bytes()
        ).hexdigest(),
        "BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX": "01" * 32,
        "BAGHOLDER_CITIC_MAIN_VNPY_PYTHON": sys.executable,
    }

    registry = BrokerRuntimeRegistry.build(
        configuration=_configuration(tmp_path),
        root=root,
        home=tmp_path / "home",
        environment=environment,
    )

    binding = registry.get("citic-main")
    assert binding.api_state is BrokerApiState.API_UNAVAILABLE
    assert binding.reason == "TEST_GATEWAY_REJECTED"
    assert binding.gateway is None
