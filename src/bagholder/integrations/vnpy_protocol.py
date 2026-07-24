"""vn.py 交易节点的带认证 JSON 消息协议。"""

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class ReplayDetected(PermissionError):
    """表示 nonce 已经使用，可能是消息重放。"""


@dataclass
class AuthenticatedProtocol:
    """使用 HMAC、时间窗口和 nonce 保护交易命令。"""

    secret: bytes
    max_age_seconds: int = 10
    _seen_nonces: set[str] = field(default_factory=set)

    def sign(
        self,
        *,
        command: str,
        payload: dict[str, Any],
        nonce: str,
        now: datetime,
    ) -> dict[str, Any]:
        """构造可验证的协议消息。"""

        body = {
            "protocol_version": "1.0",
            "command": command,
            "payload": payload,
            "nonce": nonce,
            "timestamp": now.isoformat(),
        }
        body["signature"] = self._signature(body)
        return body

    def verify(self, message: dict[str, Any], now: datetime) -> dict[str, Any]:
        """验证消息并返回负载。"""

        nonce = str(message.get("nonce", ""))
        if nonce in self._seen_nonces:
            raise ReplayDetected("检测到重复 nonce")
        timestamp = datetime.fromisoformat(str(message["timestamp"]))
        if abs((now - timestamp).total_seconds()) > self.max_age_seconds:
            raise PermissionError("交易请求超出允许的时间窗口")
        provided = str(message.get("signature", ""))
        unsigned = {key: value for key, value in message.items() if key != "signature"}
        expected = self._signature(unsigned)
        if not hmac.compare_digest(provided, expected):
            raise PermissionError("交易请求签名无效")
        self._seen_nonces.add(nonce)
        payload = message.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("交易请求负载必须是对象")
        return payload

    def _signature(self, message: dict[str, Any]) -> str:
        encoded = json.dumps(
            message,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(self.secret, encoded, hashlib.sha256).hexdigest()
