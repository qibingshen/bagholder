"""主平台到隔离 vn.py 交易节点的签名传输。"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from bagholder.integrations.vnpy_protocol import AuthenticatedProtocol


class VnpyProtocolError(RuntimeError):
    """vn.py 节点返回不符合协议。"""


class VnpyNodeError(RuntimeError):
    """vn.py 节点明确拒绝请求。"""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class VnpyTransport(Protocol):
    """签名消息传输边界。"""

    def send(self, message: dict[str, object]) -> dict[str, object]: ...


class SubprocessVnpyTransport:
    """通过独立 Python 进程向 vn.py 节点发送单条请求。"""

    def __init__(
        self,
        *,
        python_executable: str | Path,
        server_path: str | Path,
        gateway_plugin: str,
        gateway_plugin_sha256: str,
        nonce_store_path: str | Path,
        secret: bytes,
        timeout_seconds: float = 10,
    ) -> None:
        self._server_path = Path(server_path).resolve()
        self._command = [
            str(python_executable),
            str(self._server_path),
            "--request-once",
            "--gateway-plugin",
            gateway_plugin,
        ]
        self._gateway_plugin_sha256 = gateway_plugin_sha256
        self._nonce_store_path = Path(nonce_store_path).resolve()
        self._secret_hex = secret.hex()
        self._timeout_seconds = timeout_seconds

    def send(self, message: dict[str, object]) -> dict[str, object]:
        """只接受节点的一条 JSON 响应。"""

        environment = self._safe_environment()
        environment["BAGHOLDER_TRADING_NODE_SECRET_HEX"] = self._secret_hex
        environment["BAGHOLDER_VNPY_GATEWAY_SHA256"] = self._gateway_plugin_sha256
        environment["BAGHOLDER_VNPY_NONCE_STORE"] = str(self._nonce_store_path)
        try:
            completed = subprocess.run(
                self._command,
                input=json.dumps(message, ensure_ascii=False) + "\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self._timeout_seconds,
                check=False,
                cwd=self._server_path.parent,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("vn.py 交易节点超时") from error
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if completed.returncode != 0:
            raise VnpyNodeError("VNPY_NODE_FAILED")
        if len(lines) != 1:
            raise VnpyProtocolError("vn.py 节点必须只输出一条 JSON")
        try:
            response = json.loads(lines[0])
        except json.JSONDecodeError as error:
            raise VnpyProtocolError("vn.py 节点返回非法 JSON") from error
        if not isinstance(response, dict):
            raise VnpyProtocolError("vn.py 节点响应必须是对象")
        return cast(dict[str, object], response)

    @staticmethod
    def _safe_environment() -> dict[str, str]:
        allowed = {
            "COMSPEC",
            "HOME",
            "HOMEDRIVE",
            "HOMEPATH",
            "LOCALAPPDATA",
            "PATH",
            "PATHEXT",
            "SYSTEMDRIVE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        }
        return {key: value for key, value in os.environ.items() if key.upper() in allowed}


class VnpyClient:
    """签名并校验 vn.py 节点业务响应。"""

    def __init__(self, *, secret: bytes, transport: VnpyTransport) -> None:
        if len(secret) < 32:
            raise ValueError("vn.py 协议密钥至少 32 字节")
        self._protocol = AuthenticatedProtocol(secret=secret)
        self._transport = transport

    def request(
        self,
        command: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        """发送带时间窗和 nonce 的签名命令。"""

        message = self._protocol.sign(
            command=command,
            payload=payload,
            nonce=uuid4().hex,
            now=datetime.now(UTC),
        )
        response = self._transport.send(cast(dict[str, object], message))
        if response.get("ok") is not True:
            raise VnpyNodeError(str(response.get("error_code", "VNPY_REQUEST_FAILED")))
        result = response.get("result")
        if not isinstance(result, dict):
            raise VnpyProtocolError("vn.py result 必须是对象")
        return cast(dict[str, object], result)
