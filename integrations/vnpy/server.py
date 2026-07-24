"""隔离 vn.py 交易节点入口。

真实券商 SDK 由受信 ``bagholder_vnpy_*`` 插件提供；本文件只负责认证、分发和脱敏响应。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

ALLOWED_COMMANDS = {
    "HEALTH",
    "SUBMIT_ORDER",
    "CANCEL_ORDER",
    "QUERY_FUNDS",
    "QUERY_POSITIONS",
    "QUERY_ORDERS",
    "QUERY_TRADES",
}


def _signature(secret: bytes, message: dict[str, Any]) -> str:
    encoded = json.dumps(
        message,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(secret, encoded, hashlib.sha256).hexdigest()


def _verify(message: dict[str, Any], secret: bytes) -> tuple[str, dict[str, Any]]:
    command = str(message.get("command", ""))
    if command not in ALLOWED_COMMANDS:
        raise PermissionError("COMMAND_NOT_ALLOWED")
    timestamp = datetime.fromisoformat(str(message["timestamp"]))
    if timestamp.tzinfo is None:
        raise PermissionError("TIMESTAMP_INVALID")
    if abs((datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds()) > 10:
        raise PermissionError("REQUEST_EXPIRED")
    provided = str(message.get("signature", ""))
    unsigned = {key: value for key, value in message.items() if key != "signature"}
    if not hmac.compare_digest(provided, _signature(secret, unsigned)):
        raise PermissionError("SIGNATURE_INVALID")
    if not str(message.get("nonce", "")):
        raise PermissionError("NONCE_REQUIRED")
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("PAYLOAD_INVALID")
    return command, payload


def _load_gateway(plugin: str) -> object:
    if ":" not in plugin:
        raise ValueError("GATEWAY_PLUGIN_INVALID")
    module_name, factory_name = plugin.split(":", maxsplit=1)
    if not module_name.startswith("bagholder_vnpy_") or factory_name != "create_gateway":
        raise PermissionError("GATEWAY_PLUGIN_NOT_TRUSTED")
    module = importlib.import_module(module_name)
    factory = getattr(module, factory_name)
    gateway = factory()
    return gateway


def _dispatch(gateway: object, command: str, payload: dict[str, Any]) -> object:
    if command == "HEALTH":
        return gateway.health()  # type: ignore[attr-defined]
    if command == "SUBMIT_ORDER":
        request = payload.get("request")
        if not isinstance(request, dict):
            raise ValueError("ORDER_REQUEST_INVALID")
        return gateway.submit_order(request)  # type: ignore[attr-defined]
    if command == "CANCEL_ORDER":
        return gateway.cancel_order(  # type: ignore[attr-defined]
            str(payload["account_id"]),
            str(payload["broker_order_id"]),
        )
    account_id = str(payload["account_id"])
    methods = {
        "QUERY_FUNDS": "query_funds",
        "QUERY_POSITIONS": "query_positions",
        "QUERY_ORDERS": "query_orders",
        "QUERY_TRADES": "query_trades",
    }
    method = getattr(gateway, methods[command])
    return method(account_id)


def _request_once(plugin: str) -> int:
    secret_hex = os.getenv("BAGHOLDER_TRADING_NODE_SECRET_HEX", "")
    try:
        secret = bytes.fromhex(secret_hex)
    except ValueError:
        secret = b""
    if len(secret) < 32:
        raise SystemExit("交易节点密钥未配置或长度不足")
    line = sys.stdin.readline()
    try:
        message = json.loads(line)
        if not isinstance(message, dict):
            raise ValueError("REQUEST_INVALID")
        command, payload = _verify(message, secret)
        result = _dispatch(_load_gateway(plugin), command, payload)
        response = {"ok": True, "result": result}
    except Exception as error:
        print(f"vn.py request failed: {type(error).__name__}", file=sys.stderr)
        response = {"ok": False, "error_code": str(error) or "VNPY_REQUEST_FAILED"}
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """运行健康检查或处理一条经过认证的 Gateway 请求。"""

    parser = argparse.ArgumentParser(prog="bagholder-vnpy-node")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--request-once", action="store_true")
    parser.add_argument("--gateway-plugin")
    args = parser.parse_args(argv)

    if args.health and not args.gateway_plugin:
        print(
            json.dumps(
                {
                    "service": "vnpy-trading-node",
                    "status": "API_UNAVAILABLE",
                    "live_orders": False,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.request_once:
        if not args.gateway_plugin:
            raise SystemExit("未配置受信券商 Gateway")
        return _request_once(str(args.gateway_plugin))
    raise SystemExit("必须指定 --health 或 --request-once")


if __name__ == "__main__":
    raise SystemExit(main())
