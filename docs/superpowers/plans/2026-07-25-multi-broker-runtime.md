# Multi-Broker Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single global vn.py Gateway with account-driven routing for CITIC and Guotai Haitong, expose truthful per-account status, and require explicit broker confirmation before any LIVE approval.

**Architecture:** Load non-secret account metadata from `config/brokers/*.json`, resolve each account's Gateway settings from its environment prefix, and build a fail-closed `BrokerRuntimeRegistry`. PAPER keeps its existing executor; LIVE resolves the proposal account through an `AccountRoutedLiveExecutionService`, while the CLI validates `--broker` against the stored account before interactive confirmation.

**Tech Stack:** Python 3.12, Pydantic 2, dataclasses, SQLite, JSON configuration, vn.py 4.4.0 isolated subprocess, pytest, Ruff, mypy strict.

## Global Constraints

- `BAGHOLDER_LIVE_ENABLED` is the platform-wide LIVE switch and defaults to false.
- Each broker account has an independent LIVE switch and it defaults to false.
- Broker configuration files contain no secret, password, token, API key, or session value.
- LIVE execution always resolves by `account_id`; there is no default Gateway and no fallback to another account.
- A test Gateway, an identity mismatch, a missing capability, or an invalid plugin digest can never produce `READY`.
- LIVE failure never falls back to PAPER.
- The main platform, TradingAgents, and vn.py remain separate Python 3.12 environments.
- All production behavior is implemented test-first and every task ends with a focused commit.

---

## File Structure

### Create

- `src/bagholder/adapters/broker/broker_config.py`: immutable account configuration contracts and directory loader.
- `src/bagholder/adapters/broker/broker_runtime_registry.py`: account environment resolution, Gateway health validation, and account lookup.
- `tests/unit/test_broker_config.py`: JSON validation, isolation, and duplicate handling.
- `tests/unit/test_broker_runtime_registry.py`: per-account construction and health-state rules.
- `tests/integration/test_multi_broker_routing.py`: account-specific LIVE executor routing.

### Modify

- `src/bagholder/application/execution_service.py`: add `AccountRoutedLiveExecutionService`.
- `src/bagholder/runtime.py`: build and consume `BrokerRuntimeRegistry`.
- `src/bagholder/bootstrap.py`: truthful status and explicit `--broker` validation.
- `src/bagholder/testing/fake_gateway.py`: support multiple recording account Gateways in tests.
- `integrations/vnpy/bagholder_vnpy_fake.py`: return the complete health contract.
- `config/brokers/citic.json`: add currency and environment prefix; remove static runtime state.
- `config/brokers/guotai_haitong.json`: add currency and environment prefix; remove static runtime state.
- `tests/unit/test_bootstrap.py`: dynamic status and broker confirmation behavior.
- `tests/integration/test_live_execution_gate.py`: preserve fail-closed routing gates.
- `tests/contract/test_vnpy_gateway_contract.py`: complete Gateway identity/capability health contract.
- `.env.example`: replace single-account Gateway variables with two account prefixes.
- `README.md`: document multi-account configuration and LIVE commands.

---

### Task 1: Broker Account Configuration Loader

**Files:**
- Create: `src/bagholder/adapters/broker/broker_config.py`
- Create: `tests/unit/test_broker_config.py`

**Interfaces:**
- Produces: `BrokerAccountConfig`
- Produces: `BrokerConfigurationError`
- Produces: `BrokerConfigurationSet`
- Produces: `BrokerConfigLoader.load(directory: Path) -> BrokerConfigurationSet`
- Consumes: `bagholder.domain.broker.BrokerCode`

- [ ] **Step 1: Write failing tests for valid account configuration**

Add:

```python
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
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_broker_config.py::test_按文件名稳定加载两个券商账户 -q
```

Expected: FAIL because `broker_config` does not exist.

- [ ] **Step 3: Implement immutable configuration contracts and one-file parsing**

Create:

```python
"""券商账户非敏感配置与目录加载。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from bagholder.domain.broker import BrokerCode

CAPABILITY_NAMES = frozenset(
    {
        "live_orders",
        "cancel",
        "funds_query",
        "positions_query",
        "orders_query",
        "trades_query",
        "market_data",
    }
)
_ACCOUNT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_PREFIX_PATTERN = re.compile(r"^BAGHOLDER_[A-Z0-9_]+$")


@dataclass(frozen=True, slots=True)
class BrokerAccountConfig:
    account_id: str
    broker_code: BrokerCode
    display_name: str
    currency: str
    environment_prefix: str
    required_capabilities: frozenset[str]


@dataclass(frozen=True, slots=True)
class BrokerConfigurationError:
    source_file: str
    error_code: str


@dataclass(frozen=True, slots=True)
class BrokerConfigurationSet:
    accounts: tuple[BrokerAccountConfig, ...]
    errors: tuple[BrokerConfigurationError, ...]


class BrokerConfigLoader:
    def load(self, directory: Path) -> BrokerConfigurationSet:
        if not directory.is_dir():
            return BrokerConfigurationSet(
                (),
                (BrokerConfigurationError(directory.name, "CONFIG_DIRECTORY_MISSING"),),
            )
        accounts: list[tuple[Path, BrokerAccountConfig]] = []
        errors: list[BrokerConfigurationError] = []
        for path in sorted(directory.glob("*.json")):
            try:
                accounts.append((path, self._parse(path)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                errors.append(
                    BrokerConfigurationError(path.name, "BROKER_CONFIG_INVALID")
                )
        valid, duplicate_errors = self._remove_duplicates(accounts)
        errors.extend(duplicate_errors)
        return BrokerConfigurationSet(
            tuple(item for _, item in valid),
            tuple(errors),
        )

    def _parse(self, path: Path) -> BrokerAccountConfig:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("配置根对象必须是对象")
        account_id = str(payload["account_id"])
        prefix = str(payload["environment_prefix"])
        capabilities_raw = payload["required_capabilities"]
        if not _ACCOUNT_PATTERN.fullmatch(account_id):
            raise ValueError("账户 ID 无效")
        if not _PREFIX_PATTERN.fullmatch(prefix):
            raise ValueError("环境前缀无效")
        if payload["currency"] != "CNY":
            raise ValueError("币种无效")
        if not isinstance(capabilities_raw, list):
            raise TypeError("能力必须是数组")
        capabilities = [str(value) for value in capabilities_raw]
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("能力重复")
        if not set(capabilities).issubset(CAPABILITY_NAMES):
            raise ValueError("能力未知")
        return BrokerAccountConfig(
            account_id=account_id,
            broker_code=BrokerCode(str(payload["broker_code"])),
            display_name=str(payload["display_name"]),
            currency="CNY",
            environment_prefix=prefix,
            required_capabilities=frozenset(capabilities),
        )

    @staticmethod
    def _remove_duplicates(
        accounts: list[tuple[Path, BrokerAccountConfig]],
    ) -> tuple[
        list[tuple[Path, BrokerAccountConfig]],
        list[BrokerConfigurationError],
    ]:
        duplicate_accounts = {
            item.account_id
            for _, item in accounts
            if sum(other.account_id == item.account_id for _, other in accounts) > 1
        }
        duplicate_prefixes = {
            item.environment_prefix
            for _, item in accounts
            if sum(
                other.environment_prefix == item.environment_prefix
                for _, other in accounts
            )
            > 1
        }
        valid: list[tuple[Path, BrokerAccountConfig]] = []
        errors: list[BrokerConfigurationError] = []
        for path, item in accounts:
            if item.account_id in duplicate_accounts:
                errors.append(
                    BrokerConfigurationError(path.name, "DUPLICATE_ACCOUNT_CONFIG")
                )
            elif item.environment_prefix in duplicate_prefixes:
                errors.append(
                    BrokerConfigurationError(
                        path.name,
                        "DUPLICATE_ENVIRONMENT_PREFIX",
                    )
                )
            else:
                valid.append((path, item))
        return valid, errors
```

- [ ] **Step 4: Run the valid-load test and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Add failing validation and isolation tests**

Add:

```python
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
```

- [ ] **Step 6: Run all loader tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_broker_config.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 1**

```powershell
git add src/bagholder/adapters/broker/broker_config.py tests/unit/test_broker_config.py
git commit -m "feat: load broker account configurations"
```

---

### Task 2: Per-Account Gateway Runtime Registry

**Files:**
- Create: `src/bagholder/adapters/broker/broker_runtime_registry.py`
- Create: `tests/unit/test_broker_runtime_registry.py`
- Modify: `integrations/vnpy/bagholder_vnpy_fake.py`
- Modify: `tests/contract/test_vnpy_gateway_contract.py`

**Interfaces:**
- Consumes: `BrokerConfigurationSet`
- Consumes: `BrokerAccountConfig`
- Produces: `BrokerRuntimeBinding`
- Produces: `BrokerRuntimeRegistry.build(...) -> BrokerRuntimeRegistry`
- Produces: `BrokerRuntimeRegistry.get(account_id) -> BrokerRuntimeBinding`
- Produces: `GatewayBuilder`

- [ ] **Step 1: Write a failing test for independent account states**

Create:

```python
from collections.abc import Mapping
from pathlib import Path


class StubGateway:
    def __init__(self, health: dict[str, object]) -> None:
        self._health = health

    def health(self) -> dict[str, object]:
        return self._health


def _configuration(tmp_path: Path):
    import json

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
```

- [ ] **Step 2: Run the focused registry test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_broker_runtime_registry.py::test_两个账户独立构建状态 -q
```

Expected: FAIL because the registry module does not exist.

- [ ] **Step 3: Implement settings, binding, lookup, and injected building**

Create:

```python
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
    live_enabled: bool
    plugin: str
    plugin_sha256: str
    secret_hex: str
    python_executable: str


@dataclass(frozen=True, slots=True)
class BrokerRuntimeBinding:
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
    ) -> "BrokerRuntimeRegistry":
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
```

Add private helpers in the same file:

```python
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
        code = getattr(error, "error_code", "")
        known = {
            "GATEWAY_PLUGIN_HASH_MISMATCH",
            "GATEWAY_PLUGIN_HASH_REQUIRED",
            "GATEWAY_PLUGIN_NOT_TRUSTED",
        }
        message = str(error)
        if message == "GATEWAY_RUNTIME_MISSING":
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
            if str(code) in known
            else BrokerApiState.DISCONNECTED
        )
        reason = str(code) if str(code) in known else "GATEWAY_HEALTH_FAILED"
        return BrokerRuntimeBinding(
            config,
            settings.live_enabled,
            None,
            state,
            {},
            reason,
        )
    reason = _health_error(config, health)
    if reason is not None:
        return BrokerRuntimeBinding(
            config,
            settings.live_enabled,
            None,
            BrokerApiState.API_UNAVAILABLE,
            {},
            reason,
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
```

Implement the real builder:

```python
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
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Add failing health identity, test-plugin, and isolation tests**

Add:

```python
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
```

- [ ] **Step 6: Run all registry tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_broker_runtime_registry.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Extend the fake vn.py health response test-first**

First add to `tests/contract/test_vnpy_gateway_contract.py`:

```python
def test_fake_gateway_暴露完整身份和能力(tmp_path: Path) -> None:
    health = _gateway(tmp_path).health()

    assert health["broker_code"] == "CITIC"
    assert health["account_ids"] == ["citic-main"]
    assert set(health["capabilities"]) == {
        "live_orders",
        "cancel",
        "funds_query",
        "positions_query",
        "orders_query",
        "trades_query",
        "market_data",
    }
    assert health["test_plugin"] is True
```

Run the test and verify it fails because the fields are absent. Then change
`integrations/vnpy/bagholder_vnpy_fake.py` health result to:

```python
return {
    "status": "READY",
    "broker_code": "CITIC",
    "account_ids": ["citic-main"],
    "live_orders": True,
    "capabilities": [
        "live_orders",
        "cancel",
        "funds_query",
        "positions_query",
        "orders_query",
        "trades_query",
        "market_data",
    ],
    "reconciled": True,
    "market_data_ready": True,
    "test_plugin": True,
}
```

Re-run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\contract\test_vnpy_gateway_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 2**

```powershell
git add src/bagholder/adapters/broker/broker_runtime_registry.py tests/unit/test_broker_runtime_registry.py integrations/vnpy/bagholder_vnpy_fake.py tests/contract/test_vnpy_gateway_contract.py
git commit -m "feat: build per-account broker runtimes"
```

---

### Task 3: Account-Routed LIVE Execution and Runtime Wiring

**Files:**
- Modify: `src/bagholder/application/execution_service.py`
- Modify: `src/bagholder/runtime.py`
- Create: `tests/integration/test_multi_broker_routing.py`
- Modify: `tests/integration/test_live_execution_gate.py`

**Interfaces:**
- Consumes: `BrokerRuntimeRegistry`
- Produces: `AccountRoutedLiveExecutionService.submit(request, now)`
- Produces: `PlatformRuntime.broker_binding(account_id)`
- Produces: account-aware `PlatformRuntime.live_gate_context(...)`

- [ ] **Step 1: Write a failing test proving only the proposal account Gateway runs**

Create:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

NOW = datetime(2026, 7, 25, 5, tzinfo=UTC)


class RecordingGateway:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.calls = 0

    def submit(self, request):
        from bagholder.domain.broker import BrokerOrderReceipt

        self.calls += 1
        return BrokerOrderReceipt(
            account_id=request.proposal.account_id,
            broker_order_id=f"{self.prefix}-{self.calls}",
            accepted=True,
            status="SUBMITTED",
        )


def _request(account_id: str):
    from bagholder.contracts.live_trading import (
        ExecutionMode,
        ExecutionRequest,
        OrderApproval,
        OrderProposal,
        OrderSide,
        RiskVerdict,
    )

    proposal = OrderProposal(
        proposal_id=uuid4(),
        decision_id=uuid4(),
        account_id=account_id,
        security_key="CN:600000.SH",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10"),
        mode=ExecutionMode.LIVE,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=2),
    )
    return ExecutionRequest(
        request_id=uuid4(),
        idempotency_key=f"route-{account_id}-0123456789",
        proposal=proposal,
        risk_verdict=RiskVerdict(
            verdict_id=uuid4(),
            proposal_id=proposal.proposal_id,
            allowed=True,
            rule_version="risk-v1",
            blocked_reasons=[],
            checked_at=NOW,
        ),
        approval=OrderApproval(
            approval_id=uuid4(),
            proposal_id=proposal.proposal_id,
            approver="LOCAL_USER",
            approved=True,
            approved_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        ),
        correlation_id=uuid4(),
    )


def test_live_订单只调用提案账户_gateway() -> None:
    from bagholder.adapters.broker.broker_config import BrokerAccountConfig
    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeBinding,
        BrokerRuntimeRegistry,
    )
    from bagholder.application.execution_service import (
        AccountRoutedLiveExecutionService,
    )
    from bagholder.domain.broker import BrokerApiState, BrokerCode
    from bagholder.infrastructure.in_memory import InMemoryTradingRepository

    citic = RecordingGateway("CITIC")
    guotai = RecordingGateway("GUOTAI")

    def binding(account_id, broker, gateway):
        config = BrokerAccountConfig(
            account_id,
            broker,
            broker.value,
            "CNY",
            f"BAGHOLDER_{broker.value}",
            frozenset({"live_orders"}),
        )
        return BrokerRuntimeBinding(
            config,
            True,
            gateway,
            BrokerApiState.READY,
            {"live_orders": True},
            None,
        )

    registry = BrokerRuntimeRegistry(
        (
            binding("citic-main", BrokerCode.CITIC, citic),
            binding(
                "guotai-haitong-main",
                BrokerCode.GUOTAI_HAITONG,
                guotai,
            ),
        ),
        (),
    )
    service = AccountRoutedLiveExecutionService(
        InMemoryTradingRepository(),
        registry,
    )

    receipt = service.submit(_request("guotai-haitong-main"), NOW)

    assert receipt.broker_order_id == "GUOTAI-1"
    assert citic.calls == 0
    assert guotai.calls == 1
```

- [ ] **Step 2: Run the routing test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_multi_broker_routing.py::test_live_订单只调用提案账户_gateway -q
```

Expected: FAIL because `AccountRoutedLiveExecutionService` is absent.

- [ ] **Step 3: Implement the routed executor**

Add to `execution_service.py`:

```python
class AccountRoutedLiveExecutionService:
    """按订单账户选择唯一真实 Gateway。"""

    def __init__(
        self,
        repository: TradingRepository,
        registry: "BrokerRuntimeRegistry",
    ) -> None:
        self._repository = repository
        self._registry = registry

    def submit(
        self,
        request: ExecutionRequest,
        now: datetime,
    ) -> BrokerOrderReceipt:
        try:
            binding = self._registry.get(request.proposal.account_id)
        except LookupError as error:
            raise LiveBlockedError("BROKER_ACCOUNT_NOT_FOUND") from error
        if (
            binding.api_state is not BrokerApiState.READY
            or binding.gateway is None
        ):
            raise LiveBlockedError("BROKER_API_UNAVAILABLE")
        return LiveExecutionService(
            self._repository,
            binding.gateway,
        ).submit(request, now)
```

Use `TYPE_CHECKING` to import `BrokerRuntimeRegistry` without creating an application-to-adapter runtime cycle.

- [ ] **Step 4: Run the routing test and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Add a failing test for unknown/unavailable account isolation**

Add:

```python
def test_未知账户不调用任何_gateway() -> None:
    import pytest

    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeRegistry,
    )
    from bagholder.application.execution_service import (
        AccountRoutedLiveExecutionService,
        LiveBlockedError,
    )
    from bagholder.infrastructure.in_memory import InMemoryTradingRepository

    service = AccountRoutedLiveExecutionService(
        InMemoryTradingRepository(),
        BrokerRuntimeRegistry((), ()),
    )

    with pytest.raises(LiveBlockedError) as captured:
        service.submit(_request("missing-account"), NOW)

    assert captured.value.error_code == "BROKER_ACCOUNT_NOT_FOUND"
```

Run the file and verify both tests pass.

- [ ] **Step 6: Refactor `PlatformRuntime` to consume the registry**

Change the runtime dataclass fields to:

```python
broker_registry: BrokerRuntimeRegistry
system_live_enabled: bool
```

Implement:

```python
def broker_binding(self, account_id: str) -> BrokerRuntimeBinding:
    return self.broker_registry.get(account_id)


def live_gate_context(
    self,
    account_id: str,
    *,
    interactive_confirmation: bool,
) -> LiveGateContext:
    binding = self.broker_binding(account_id)
    return LiveGateContext(
        system_live_enabled=self.system_live_enabled,
        account_live_enabled=binding.account_live_enabled,
        broker_api_state=binding.api_state,
        supports_live_orders=bool(binding.health.get("live_orders", False)),
        reconciled=bool(binding.health.get("reconciled", False)),
        interactive_confirmation=interactive_confirmation,
    )
```

Update `live_risk_context` to resolve one binding and use only
`binding.gateway` and `binding.health`.

Replace `_build_live_gateway` in `build_runtime` with:

```python
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
```

Pass `registry` into `PlatformRuntime`.

- [ ] **Step 7: Run focused runtime and gate regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_multi_broker_routing.py tests\integration\test_live_execution_gate.py tests\integration\test_pipeline.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Run mypy before committing**

Run:

```powershell
.\.venv\Scripts\python.exe -m mypy src
```

Expected: success with no issues.

- [ ] **Step 9: Commit Task 3**

```powershell
git add src/bagholder/application/execution_service.py src/bagholder/runtime.py tests/integration/test_multi_broker_routing.py tests/integration/test_live_execution_gate.py tests/integration/test_pipeline.py
git commit -m "feat: route live execution by broker account"
```

---

### Task 4: Truthful Status and Explicit Broker Confirmation

**Files:**
- Modify: `src/bagholder/bootstrap.py`
- Modify: `tests/unit/test_bootstrap.py`

**Interfaces:**
- Consumes: `PlatformRuntime.broker_registry`
- Produces: `_status_payload(runtime: PlatformRuntime) -> dict[str, object]`
- Adds: `pipeline approve --broker {CITIC,GUOTAI_HAITONG}`
- Adds stable errors: `BROKER_CONFIRMATION_REQUIRED`, `BROKER_ACCOUNT_MISMATCH`, `BROKER_NOT_ALLOWED_FOR_PAPER`

- [ ] **Step 1: Replace the static-status test with a failing dynamic-status test**

Add this test helper:

```python
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
    assert all(item["api_state"] == "API_UNAVAILABLE" for item in accounts.values())
```

- [ ] **Step 2: Run the status test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_bootstrap.py::test_status_显示真实总开关和账户开关 -q
```

Expected: FAIL because status is hard-coded false.

- [ ] **Step 3: Build runtime for status and serialize bindings**

Replace `_status_payload()` with:

```python
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
```

Change `main` so `doctor` remains environment-only, while `status` is handled inside the existing `try` after `build_runtime()`:

```python
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
```

- [ ] **Step 4: Run the status test and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Write failing tests for broker confirmation**

Add:

```python
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
```

Also add:

```python
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

    from bagholder.adapters.broker.broker_config import (
        BrokerAccountConfig,
    )
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
```

- [ ] **Step 6: Run the broker-confirmation tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_bootstrap.py -k "券商" -q
```

Expected: FAIL because `--broker` is not registered and no validation exists.

- [ ] **Step 7: Add the CLI option and validation**

Import `BrokerCode`. Add:

```python
pipeline_approve.add_argument(
    "--broker",
    choices=[item.value for item in BrokerCode],
)
```

Add helpers:

```python
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
```

Call `_validate_broker_argument(mode, args.broker)` before `pipeline.show`.
Then use this LIVE branch after loading the run:

```python
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
```

Do not retain the old single-Gateway branch. PAPER with no broker continues
to approve through its existing path.

If the mode is PAPER and `args.broker` is provided, the early helper raises:

```python
if mode is ExecutionMode.PAPER and args.broker is not None:
    raise LiveBlockedError("BROKER_NOT_ALLOWED_FOR_PAPER")
```

Add and use this pure helper:

```python
def _live_confirmation_text(
    broker_code: BrokerCode,
    proposal: OrderProposal,
) -> str:
    return (
    f"{broker_code.value} {proposal.account_id} "
    f"{proposal.security_key} {proposal.side.value} {proposal.quantity}"
    )
```

Change `_confirm_live` to accept `broker_code: BrokerCode` and set:

```python
expected = _live_confirmation_text(broker_code, proposal)
```

- [ ] **Step 8: Run all bootstrap and pipeline tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_bootstrap.py tests\integration\test_pipeline.py tests\integration\test_live_execution_gate.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Verify status output contains no secret values**

Add:

```python
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
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_bootstrap.py::test_status_不输出账户插件摘要或密钥 -q
```

Expected: PASS.

- [ ] **Step 10: Commit Task 4**

```powershell
git add src/bagholder/bootstrap.py tests/unit/test_bootstrap.py
git commit -m "feat: expose truthful broker account status"
```

---

### Task 5: Migrate Broker Profiles and Operator Documentation

**Files:**
- Modify: `config/brokers/citic.json`
- Modify: `config/brokers/guotai_haitong.json`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/contract/test_broker_profiles.py`

**Interfaces:**
- Consumes: `BrokerConfigLoader`
- Produces: two valid default account profiles
- Produces: documented account-specific environment configuration

- [ ] **Step 1: Write a failing contract test for repository profiles**

Replace static-account-only assertions with:

```python
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
```

- [ ] **Step 2: Run the profile test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\contract\test_broker_profiles.py::test_仓库默认券商配置可被统一加载 -q
```

Expected: FAIL because the current JSON files lack `currency` and `environment_prefix`.

- [ ] **Step 3: Migrate both JSON profiles**

Use the exact schema from the design. Remove `execution_mode` and `api_state`; add:

```json
"currency": "CNY",
"environment_prefix": "BAGHOLDER_CITIC_MAIN"
```

for CITIC and:

```json
"currency": "CNY",
"environment_prefix": "BAGHOLDER_GUOTAI_HAITONG_MAIN"
```

for Guotai Haitong. Add `"market_data"` to both required capability lists.

- [ ] **Step 4: Run the profile test and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Replace legacy variables in `.env.example`**

Keep:

```text
BAGHOLDER_LIVE_ENABLED=false
```

Add:

```text
BAGHOLDER_CITIC_MAIN_LIVE_ENABLED=false
BAGHOLDER_CITIC_MAIN_VNPY_PYTHON=.runtime/vnpy/Scripts/python.exe
BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN=
BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256=
BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX=

BAGHOLDER_GUOTAI_HAITONG_MAIN_LIVE_ENABLED=false
BAGHOLDER_GUOTAI_HAITONG_MAIN_VNPY_PYTHON=.runtime/vnpy/Scripts/python.exe
BAGHOLDER_GUOTAI_HAITONG_MAIN_GATEWAY_PLUGIN=
BAGHOLDER_GUOTAI_HAITONG_MAIN_GATEWAY_SHA256=
BAGHOLDER_GUOTAI_HAITONG_MAIN_TRADING_NODE_SECRET_HEX=
```

Remove the old single-account Gateway and account LIVE variables.

- [ ] **Step 6: Update README commands and safety explanation**

Document:

```powershell
$env:BAGHOLDER_LIVE_ENABLED = "true"
$env:BAGHOLDER_CITIC_MAIN_LIVE_ENABLED = "true"
$env:BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN = "bagholder_vnpy_citic:create_gateway"
$env:BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256 = "<受信插件 SHA-256>"
$env:BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX = "<系统凭据存储注入>"

.\.venv\Scripts\bagholder.exe pipeline approve <运行ID> `
  --mode LIVE `
  --broker CITIC `
  --confirm-live `
  --json
```

Add the equivalent Guotai Haitong variable names and explain that both accounts can be configured concurrently and fail independently.

- [ ] **Step 7: Run contracts and documentation consistency checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\contract\test_broker_profiles.py tests\unit\test_bootstrap.py -q
rg -n "BAGHOLDER_ACCOUNT_LIVE_ENABLED|^BAGHOLDER_VNPY_GATEWAY_PLUGIN|^BAGHOLDER_TRADING_NODE_SECRET_HEX" .env.example README.md
```

Expected: tests pass; `rg` returns no legacy variable declarations.

- [ ] **Step 8: Commit Task 5**

```powershell
git add config/brokers/citic.json config/brokers/guotai_haitong.json .env.example README.md tests/contract/test_broker_profiles.py
git commit -m "docs: configure citic and guotai account routing"
```

---

### Task 6: Full Verification and Safety Acceptance

**Files:**
- Modify only if a verification command exposes a defect, following a new RED-GREEN cycle.

**Interfaces:**
- Validates all interfaces produced by Tasks 1-5.

- [ ] **Step 1: Run the full deterministic test suite with coverage**

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=bagholder --cov-report=term-missing
```

Expected: no failures; the live-data test is the only environment-gated skip.

- [ ] **Step 2: Run static verification**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pip check
.\.runtime\tradingagents\Scripts\python.exe -m pip check
.\.runtime\vnpy\Scripts\python.exe -m pip check
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 3: Build the wheel**

```powershell
$wheelDir = Join-Path $env:TEMP ("bagholder-wheel-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $wheelDir | Out-Null
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir $wheelDir
```

Expected: one `bagholder_trading_platform-0.1.0-py3-none-any.whl`.

- [ ] **Step 4: Verify default status and health**

```powershell
.\.venv\Scripts\bagholder.exe doctor --json
.\.venv\Scripts\bagholder.exe status --json
```

Expected:

- all three Python environments are ready;
- global LIVE is false;
- CITIC and Guotai Haitong both appear;
- both account LIVE switches are false;
- both accounts remain `API_UNAVAILABLE`;
- both reasons are `GATEWAY_CONFIG_INCOMPLETE`.

- [ ] **Step 5: Verify truthful switches without a Gateway**

```powershell
$env:BAGHOLDER_LIVE_ENABLED = "true"
$env:BAGHOLDER_CITIC_MAIN_LIVE_ENABLED = "true"
try {
  .\.venv\Scripts\bagholder.exe status --json
} finally {
  Remove-Item Env:BAGHOLDER_LIVE_ENABLED -ErrorAction SilentlyContinue
  Remove-Item Env:BAGHOLDER_CITIC_MAIN_LIVE_ENABLED -ErrorAction SilentlyContinue
}
```

Expected: global and CITIC account switches show true, but CITIC remains
`API_UNAVAILABLE` because no private Gateway is configured.

- [ ] **Step 6: Verify the test Gateway is rejected as production**

Run:

```powershell
$pluginHash = (
  Get-FileHash integrations\vnpy\bagholder_vnpy_fake.py -Algorithm SHA256
).Hash.ToLowerInvariant()
$env:BAGHOLDER_CITIC_MAIN_LIVE_ENABLED = "true"
$env:BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN = "bagholder_vnpy_fake:create_gateway"
$env:BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256 = $pluginHash
$env:BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX = ("01" * 32)
$env:BAGHOLDER_CITIC_MAIN_VNPY_PYTHON = (
  Resolve-Path .\.runtime\vnpy\Scripts\python.exe
).Path
try {
  .\.venv\Scripts\bagholder.exe status --json
} finally {
  "BAGHOLDER_CITIC_MAIN_LIVE_ENABLED",
  "BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN",
  "BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256",
  "BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX",
  "BAGHOLDER_CITIC_MAIN_VNPY_PYTHON" | ForEach-Object {
    Remove-Item "Env:$_" -ErrorAction SilentlyContinue
  }
}
```

Expected:

- CITIC reason is `TEST_GATEWAY_REJECTED`;
- CITIC never becomes `READY`;
- Guotai Haitong remains independently `API_UNAVAILABLE`;
- no order or execution receipt is written.

- [ ] **Step 7: Run the explicit real public-data smoke**

```powershell
$env:RUN_LIVE_DATA_TESTS = "1"
try {
  .\.venv\Scripts\python.exe -m pytest tests\live\test_astock_market_data.py -q
} finally {
  Remove-Item Env:RUN_LIVE_DATA_TESTS -ErrorAction SilentlyContinue
}
```

Expected: one test passes, evidence is written in pytest temporary storage, and no model or order is invoked.

- [ ] **Step 8: Scan for accidentally tracked credentials**

```powershell
rg -n --hidden `
  -g "!/.git/**" -g "!/.venv/**" -g "!/.runtime/**" -g "!/var/**" `
  -e "AKIA[0-9A-Z]{16}" `
  -e "sk-[A-Za-z0-9_-]{20,}" `
  -e "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----" `
  .
```

Expected: no credentials.

- [ ] **Step 9: Confirm a clean worktree**

```powershell
git status --short
git log --oneline -8
```

Expected: clean worktree and five implementation commits after the design and plan commits.
