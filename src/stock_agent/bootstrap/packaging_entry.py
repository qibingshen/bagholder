"""打包产物的桌面启动入口。"""

from __future__ import annotations

import sys

from stock_agent.desktop.app_shell import run_desktop_app


def main() -> int:
    """启动 PySide6 桌面应用。"""

    return run_desktop_app(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
