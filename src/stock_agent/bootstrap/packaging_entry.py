"""打包产物的最小启动入口。"""

from __future__ import annotations

from stock_agent.bootstrap.entrypoints import (
    DESKTOP_ENTRY,
    LOCAL_SERVICE_ENTRY,
    MCP_ENTRY,
    TRAINING_ENTRY,
    WORKER_ENTRY,
)


def main() -> int:
    """输出当前安装包包含的本机进程入口名称。"""

    entries = (DESKTOP_ENTRY, LOCAL_SERVICE_ENTRY, WORKER_ENTRY, TRAINING_ENTRY, MCP_ENTRY)
    print("bagholder entries: " + ", ".join(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
