"""账户级 Gateway 装配、健康校验和运行状态。"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from bagholder.adapters.broker.broker_config import (
    BrokerAccountConfig,
    BrokerConfigurationError,
    BrokerConfigurationSet,
)
from bagholder.domain.broker import BrokerApiState, BrokerGateway


@dataclass(frozen=True, slots=True)
class AccountGatewaySettings:
    """从账户环境前缀解析出的敏感运行参数。"""

    live_enabled: bool
    plugin: str
    plugin_sha256: str
    secret_hex: str
    python_executable: str


@dataclass(frozen=True, slots=True)
class BrokerRuntimeBinding:
    """一个账户当前可安全暴露的 Gateway 运行状态。"""

    config: BrokerAccountConfig
    account_live_enabled: bool
    gateway: BrokerGateway | None
    api_state: BrokerApiState
    health: dict[str, object]
    reason: str | None


GatewayBuilder = Callable[
    [BrokerAccountConfig, AccountGatewaySettings, Path, Path],
    BrokerGateway,
]


class BrokerRuntimeRegistry:
    """按账户隔离保存券商 Gateway 和健康状态。"""

    def __init__(
        self,
        bindings: tuple[BrokerRuntimeBinding, ...],
        errors: tuple[BrokerConfigurationError, ...],
    ) -> None:
        self._bindings = bindings
        self._errors = errors
        self._by_account = {item.config.account_id: item for item in bindings}

    @classmethod
    def build(
        cls,
        *,
        configuration: BrokerConfigurationSet,
        root: Path,
        home: Path,
        environment: Mapping[str, str] | None = None,
        gateway_builder: GatewayBuilder | None = None,
    ) -> BrokerRuntimeRegistry:
        """逐账户解析参数；未配置账户不调用 Gateway builder。"""

        source = os.environ if environment is None else environment
        builder = gateway_builder or _build_subprocess_gateway
        bindings = tuple(
            _build_binding(config, source, root, home, builder)
            for config in configuration.accounts
        )
        return cls(bindings, configuration.errors)

    def get(self, account_id: str) -> BrokerRuntimeBinding:
        try:
            return self._by_account[account_id]
        except KeyError as error:
            raise LookupError("BROKER_ACCOUNT_NOT_FOUND") from error

    def bindings(self) -> tuple[BrokerRuntimeBinding, ...]:
        return self._bindings

    def configuration_errors(self) -> tuple[BrokerConfigurationError, ...]:
        return self._errors


def _env_true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _settings(
    config: BrokerAccountConfig,
    environment: Mapping[str, str],
    root: Path,
) -> AccountGatewaySettings:
    prefix = config.environment_prefix
    return AccountGatewaySettings(
        live_enabled=_env_true(environment.get(f"{prefix}_LIVE_ENABLED", "")),
        plugin=environment.get(f"{prefix}_GATEWAY_PLUGIN", "").strip(),
        plugin_sha256=environment.get(f"{prefix}_GATEWAY_SHA256", "").strip(),
        secret_hex=environment.get(
            f"{prefix}_TRADING_NODE_SECRET_HEX",
            "",
        ).strip(),
        python_executable=environment.get(
            f"{prefix}_VNPY_PYTHON",
            str(root / ".runtime" / "vnpy" / "Scripts" / "python.exe"),
        ),
    )


def _complete(settings: AccountGatewaySettings) -> bool:
    if not settings.plugin or len(settings.plugin_sha256) != 64:
        return False
    try:
        secret = bytes.fromhex(settings.secret_hex)
    except ValueError:
        return False
    return len(secret) >= 32


def _build_binding(
    config: BrokerAccountConfig,
    environment: Mapping[str, str],
    root: Path,
    home: Path,
    builder: GatewayBuilder,
) -> BrokerRuntimeBinding:
    settings = _settings(config, environment, root)
    if not _complete(settings):
        return BrokerRuntimeBinding(
            config,
            settings.live_enabled,
            None,
            BrokerApiState.API_UNAVAILABLE,
            {},
            "GATEWAY_CONFIG_INCOMPLETE",
        )
    try:
        gateway = builder(config, settings, root, home)
        health = gateway.health()
    except Exception as error:
        code = str(getattr(error, "error_code", ""))
        known = {
            "GATEWAY_PLUGIN_HASH_MISMATCH",
            "GATEWAY_PLUGIN_HASH_REQUIRED",
            "GATEWAY_PLUGIN_NOT_TRUSTED",
        }
        if str(error) == "GATEWAY_RUNTIME_MISSING":
            return BrokerRuntimeBinding(
                config,
                settings.live_enabled,
                None,
                BrokerApiState.API_UNAVAILABLE,
                {},
                "GATEWAY_RUNTIME_MISSING",
            )
        state = (
            BrokerApiState.API_UNAVAILABLE
            if code in known
            else BrokerApiState.DISCONNECTED
        )
        reason = code if code in known else "GATEWAY_HEALTH_FAILED"
        return BrokerRuntimeBinding(
            config,
            settings.live_enabled,
            None,
            state,
            {},
            reason,
        )
    health_reason = _health_error(config, health)
    if health_reason is not None:
        return BrokerRuntimeBinding(
            config,
            settings.live_enabled,
            None,
            BrokerApiState.API_UNAVAILABLE,
            {},
            health_reason,
        )
    return BrokerRuntimeBinding(
        config,
        settings.live_enabled,
        gateway,
        BrokerApiState.READY,
        health,
        None,
    )


def _health_error(
    config: BrokerAccountConfig,
    health: dict[str, object],
) -> str | None:
    if health.get("test_plugin") is not False:
        return "TEST_GATEWAY_REJECTED"
    account_ids = health.get("account_ids")
    if (
        health.get("broker_code") != config.broker_code.value
        or not isinstance(account_ids, list)
        or config.account_id not in account_ids
    ):
        return "GATEWAY_IDENTITY_MISMATCH"
    capabilities = health.get("capabilities")
    if not isinstance(capabilities, list) or not config.required_capabilities.issubset(
        {str(value) for value in capabilities}
    ):
        return "GATEWAY_CAPABILITY_MISSING"
    if health.get("status") != "READY" or health.get("live_orders") is not True:
        return "GATEWAY_HEALTH_FAILED"
    return None


def _build_subprocess_gateway(
    config: BrokerAccountConfig,
    settings: AccountGatewaySettings,
    root: Path,
    home: Path,
) -> BrokerGateway:
    from bagholder.adapters.broker.vnpy_gateway import VnpyBrokerGateway
    from bagholder.integrations.vnpy_client import (
        SubprocessVnpyTransport,
        VnpyClient,
    )

    python_path = Path(settings.python_executable)
    server_path = root / "integrations" / "vnpy" / "server.py"
    if not python_path.exists() or not server_path.exists():
        raise RuntimeError("GATEWAY_RUNTIME_MISSING")
    secret = bytes.fromhex(settings.secret_hex)
    transport = SubprocessVnpyTransport(
        python_executable=python_path,
        server_path=server_path,
        gateway_plugin=settings.plugin,
        gateway_plugin_sha256=settings.plugin_sha256,
        nonce_store_path=home / f"vnpy-nonces-{config.account_id}.sqlite3",
        secret=secret,
    )
    return VnpyBrokerGateway(VnpyClient(secret=secret, transport=transport))
