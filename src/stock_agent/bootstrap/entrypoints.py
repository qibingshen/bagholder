"""登记各进程的启动入口名称，具体启动行为由对应任务实现。"""

from typing import Final

LOCAL_SERVICE_ENTRY: Final = "local_service"
DESKTOP_ENTRY: Final = "desktop"
WORKER_ENTRY: Final = "worker"
TRAINING_ENTRY: Final = "training"
MCP_ENTRY: Final = "mcp"
