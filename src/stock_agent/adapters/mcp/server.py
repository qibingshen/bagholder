"""提供本机 MCP stdio 服务的受控启动入口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from stock_agent.mcp.contracts import MCPToolRegistry

MCPTransport = Literal["stdio", "local_controlled"]


@dataclass(frozen=True)
class MCPServerConfig:
    """描述 MCP Server 的本机传输和注册工具范围。"""

    transport: MCPTransport = "stdio"
    caller_host: str = "localhost"

    def __post_init__(self) -> None:
        """阻断非本机或非受控传输，避免 MCP 被远程直接调用。"""

        allowed_transports = {"stdio", "local_controlled"}
        if self.transport not in allowed_transports:
            raise ValueError("MCP Server 仅支持 stdio 或受控本机传输")
        allowed_hosts = {"localhost", "127.0.0.1", "::1"}
        if self.caller_host not in allowed_hosts:
            raise ValueError("MCP Server 只能接受本机调用")


@dataclass(frozen=True)
class MCPServer:
    """首个阶段的 MCP Server 壳层，负责暴露工具注册表和启动配置。"""

    config: MCPServerConfig
    registry: MCPToolRegistry

    @classmethod
    def create_local_stdio(cls) -> MCPServer:
        """创建默认 stdio 本机 MCP 服务实例。"""

        return cls(config=MCPServerConfig(), registry=MCPToolRegistry.default())

    @property
    def tool_names(self) -> frozenset[str]:
        """返回当前服务暴露的工具名称集合。"""

        return self.registry.tool_names


def create_stdio_server() -> MCPServer:
    """供启动脚本使用的默认工厂函数。"""

    return MCPServer.create_local_stdio()
