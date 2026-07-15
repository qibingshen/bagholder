"""集中放置操作系统差异适配器，业务层不得直接依赖平台 API。"""

from stock_agent.adapters.platform.contracts import CredentialStore, PlatformPaths

__all__ = ["CredentialStore", "PlatformPaths"]
