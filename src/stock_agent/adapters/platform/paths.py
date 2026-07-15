"""集中处理三种桌面平台的本地目录与进程互斥。"""

import json
import os
from pathlib import Path
from uuid import uuid4


class RuntimeLockError(RuntimeError):
    """表示已有桌面进程占用同一数据目录，继续运行会损害本地事实数据。"""


def data_root(path: str | None = None) -> Path:
    """返回平台推荐的数据根目录，调用者指定目录时仅用于受控测试或迁移。"""

    if path:
        root = Path(path)
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LocalStockAgent"
    elif os.uname().sysname == "Darwin":
        root = Path.home() / "Library" / "Application Support" / "LocalStockAgent"
    else:
        root = (
            Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            / "local-stock-agent"
        )
    root.mkdir(parents=True, exist_ok=True)
    return root


class RuntimeLock:
    """以原子创建的锁文件阻止多个桌面进程同时修改同一数据根目录。"""

    def __init__(self, root: Path) -> None:
        self._path = root / ".runtime.lock"
        self._token: str | None = None

    def acquire(self) -> None:
        """获取排他锁；锁已存在时不尝试覆盖，避免静默破坏另一个进程的数据。"""

        token = str(uuid4())
        try:
            descriptor = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError as error:
            raise RuntimeLockError("本地数据目录已被另一个桌面进程占用") from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
            json.dump({"token": token, "pid": os.getpid()}, lock_file)
        self._token = token

    def release(self) -> None:
        """仅删除自身创建的锁，避免进程退出时误删后来持有者的锁。"""

        if self._token is None or not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if payload.get("token") == self._token:
            self._path.unlink()
        self._token = None
