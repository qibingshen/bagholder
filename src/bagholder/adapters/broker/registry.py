"""受信券商 Gateway 注册表。"""

from dataclasses import dataclass

from bagholder.domain.broker import (
    BrokerAccount,
    BrokerApiState,
    BrokerCode,
    GatewayCapabilities,
)


@dataclass(frozen=True, slots=True)
class GatewayPlugin:
    """经过包名、版本和摘要校验的券商插件。"""

    plugin_id: str
    broker_codes: frozenset[BrokerCode]
    capabilities: GatewayCapabilities
    package_name: str
    package_version: str
    sdk_version: str
    package_sha256: str


class BrokerRegistry:
    """只从显式传入的受信插件中选择券商实现。"""

    def __init__(self, plugins: list[GatewayPlugin]) -> None:
        self._plugins = tuple(plugins)

    @staticmethod
    def default_accounts() -> tuple[BrokerAccount, ...]:
        """注册两家券商，但默认不声明 API 可用。"""

        unavailable = GatewayCapabilities(False, False, False, False, False, False, False)
        return (
            BrokerAccount(
                "citic-main",
                BrokerCode.CITIC,
                BrokerApiState.API_UNAVAILABLE,
                "CNY",
                unavailable,
            ),
            BrokerAccount(
                "guotai-haitong-main",
                BrokerCode.GUOTAI_HAITONG,
                BrokerApiState.API_UNAVAILABLE,
                "CNY",
                unavailable,
            ),
        )

    def bind(self, broker_code: BrokerCode) -> GatewayPlugin:
        """返回支持指定券商的受信插件。"""

        for plugin in self._plugins:
            if broker_code in plugin.broker_codes:
                return plugin
        raise LookupError(f"{broker_code.value} 没有可用的受信 Gateway")
