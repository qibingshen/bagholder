"""隔离 vn.py 交易节点入口。

真实券商 SDK 由受信 ``bagholder_vnpy_*`` 插件提供；本文件只负责认证、分发和脱敏响应。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib
import importlib.util
import json
import os
import sqlite3
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
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


def _claim_nonce(nonce: str, database_path: Path) -> None:
    """跨一次性子进程持久化 nonce，阻止在时间窗内重放交易指令。"""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    now_timestamp = datetime.now(UTC).timestamp()
    with sqlite3.connect(database_path, timeout=5) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS used_nonces (
                nonce TEXT PRIMARY KEY,
                claimed_at REAL NOT NULL
            )
            """
        )
        connection.execute(
            "DELETE FROM used_nonces WHERE claimed_at < ?",
            (now_timestamp - 60,),
        )
        try:
            connection.execute(
                "INSERT INTO used_nonces (nonce, claimed_at) VALUES (?, ?)",
                (nonce, now_timestamp),
            )
        except sqlite3.IntegrityError as error:
            raise PermissionError("REPLAY_DETECTED") from error


def _verify(
    message: dict[str, Any],
    secret: bytes,
    nonce_store_path: Path,
) -> tuple[str, dict[str, Any]]:
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
    nonce = str(message.get("nonce", ""))
    if not nonce:
        raise PermissionError("NONCE_REQUIRED")
    _claim_nonce(nonce, nonce_store_path)
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("PAYLOAD_INVALID")
    return command, payload


def _load_gateway(plugin: str, expected_sha256: str) -> object:
    if ":" not in plugin:
        raise ValueError("GATEWAY_PLUGIN_INVALID")
    module_name, factory_name = plugin.split(":", maxsplit=1)
    if not module_name.startswith("bagholder_vnpy_") or factory_name != "create_gateway":
        raise PermissionError("GATEWAY_PLUGIN_NOT_TRUSTED")
    if len(expected_sha256) != 64:
        raise PermissionError("GATEWAY_PLUGIN_HASH_REQUIRED")
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        raise ImportError("GATEWAY_PLUGIN_NOT_FOUND")
    actual_sha256 = hashlib.sha256(Path(spec.origin).read_bytes()).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256.lower()):
        raise PermissionError("GATEWAY_PLUGIN_HASH_MISMATCH")
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
    plugin_sha256 = os.getenv("BAGHOLDER_VNPY_GATEWAY_SHA256", "")
    nonce_store = Path(
        os.getenv("BAGHOLDER_VNPY_NONCE_STORE", "vnpy-nonces.sqlite3")
    ).resolve()
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
        command, payload = _verify(message, secret, nonce_store)
        result = _dispatch(
            _load_gateway(plugin, plugin_sha256),
            command,
            payload,
        )
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
