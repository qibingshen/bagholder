"""通过一次一请求子进程安全调用 TradingAgents-Astock。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import cast

from bagholder.contracts.market_data import (
    FetchMarketRequest,
    MarketSnapshot,
    ResearchProcessRequest,
    ResearchProcessResult,
)


class TradingAgentsProtocolError(RuntimeError):
    """TradingAgents 子进程违反 JSON Lines 协议。"""


class TradingAgentsProcessError(RuntimeError):
    """TradingAgents 子进程明确返回失败。"""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class TradingAgentsClient:
    """隔离依赖、超时和输出解析的 TradingAgents 客户端。"""

    def __init__(
        self,
        python_executable: str | Path,
        runner_path: str | Path,
        timeout_seconds: float = 120,
    ) -> None:
        self._command = [str(python_executable), str(runner_path)]
        self._timeout_seconds = timeout_seconds

    def request(self, payload: dict[str, object]) -> dict[str, object]:
        """发送单条请求并只接受单条 JSON 对象响应。"""

        try:
            completed = subprocess.run(
                self._command,
                input=json.dumps(payload, ensure_ascii=False) + "\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self._timeout_seconds,
                check=False,
                env=self._safe_environment(),
            )
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("TradingAgents 子进程超时") from error

        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if completed.returncode != 0:
            raise TradingAgentsProcessError("TRADINGAGENTS_PROCESS_FAILED")
        if len(lines) != 1:
            raise TradingAgentsProtocolError("TradingAgents 必须只输出一条 JSON")
        try:
            response = json.loads(lines[0])
        except json.JSONDecodeError as error:
            raise TradingAgentsProtocolError("TradingAgents 返回非法 JSON") from error
        if not isinstance(response, dict):
            raise TradingAgentsProtocolError("TradingAgents 响应必须是对象")
        if response.get("ok") is not True:
            code = response.get("error_code", "TRADINGAGENTS_REQUEST_FAILED")
            raise TradingAgentsProcessError(str(code))
        result = response.get("result")
        if not isinstance(result, dict):
            raise TradingAgentsProtocolError("TradingAgents result 必须是对象")
        return cast(dict[str, object], result)

    def fetch_market(self, request: FetchMarketRequest) -> MarketSnapshot:
        """拉取并校验标准化行情快照。"""

        result = self.request(
            {
                "operation": "FETCH_MARKET",
                "payload": request.model_dump(mode="json"),
            }
        )
        return MarketSnapshot.model_validate(result)

    def run_research(self, request: ResearchProcessRequest) -> ResearchProcessResult:
        """运行研究并校验白名单结果。"""

        result = self.request(
            {
                "operation": "RUN_RESEARCH",
                "payload": request.model_dump(mode="json"),
            }
        )
        return ResearchProcessResult.model_validate(result)

    @staticmethod
    def _safe_environment() -> dict[str, str]:
        """只向隔离进程传递运行所需系统字段和专用配置。"""

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
            "TRADINGAGENTS_API_KEY",
            "TRADINGAGENTS_BACKEND_URL",
            "TRADINGAGENTS_CACHE_DIR",
            "TRADINGAGENTS_LLM_PROVIDER",
            "TRADINGAGENTS_MODEL",
            "TRADINGAGENTS_RESULTS_DIR",
        }
        return {key: value for key, value in os.environ.items() if key.upper() in allowed}
