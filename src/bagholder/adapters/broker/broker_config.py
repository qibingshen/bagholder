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
    """单个券商账户的非敏感静态配置。"""

    account_id: str
    broker_code: BrokerCode
    display_name: str
    currency: str
    environment_prefix: str
    required_capabilities: frozenset[str]


@dataclass(frozen=True, slots=True)
class BrokerConfigurationError:
    """可安全返回给操作者的配置文件错误。"""

    source_file: str
    error_code: str


@dataclass(frozen=True, slots=True)
class BrokerConfigurationSet:
    """目录中独立校验后的有效账户和脱敏错误。"""

    accounts: tuple[BrokerAccountConfig, ...]
    errors: tuple[BrokerConfigurationError, ...]


class BrokerConfigLoader:
    """按文件隔离加载券商账户配置。"""

    def load(self, directory: Path) -> BrokerConfigurationSet:
        """加载目录；一个文件无效时保留其他有效账户。"""

        if not directory.is_dir():
            return BrokerConfigurationSet(
                (),
                (
                    BrokerConfigurationError(
                        directory.name,
                        "CONFIG_DIRECTORY_MISSING",
                    ),
                ),
            )
        accounts: list[tuple[Path, BrokerAccountConfig]] = []
        errors: list[BrokerConfigurationError] = []
        for path in sorted(directory.glob("*.json")):
            try:
                accounts.append((path, self._parse(path)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                errors.append(
                    BrokerConfigurationError(
                        path.name,
                        "BROKER_CONFIG_INVALID",
                    )
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
            if sum(
                other.account_id == item.account_id
                for _, other in accounts
            )
            > 1
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
                    BrokerConfigurationError(
                        path.name,
                        "DUPLICATE_ACCOUNT_CONFIG",
                    )
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
