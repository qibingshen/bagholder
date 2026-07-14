"""提供只读新浪 A 股行情 HTTP 适配器。"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from stock_agent.adapters.market_data.base import NormalizedQuote, SourceCapability
from stock_agent.contracts.common import Freshness
from stock_agent.domain.freshness import classify_freshness
from stock_agent.domain.market import InstrumentIdentity, Market

_SINA_URL_PREFIX = "http://hq.sinajs.cn/list="
_SINA_CODE_PATTERN = re.compile(r"(?P<prefix>sh|sz)(?P<display_code>[0-9]{6})\Z")
_SINA_LINE_PATTERN = re.compile(
    r'var hq_str_(?P<code>sh[0-9]{6}|sz[0-9]{6})="(?P<fields>[^"]*)";\Z'
)
_SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")


class SinaDataSourceError(RuntimeError):
    """表示新浪读取结果无法安全转换为完整规范化行情。"""


class SinaHttpAdapter:
    """通过调用方注入的读取器获取并验证新浪 A 股实时报价。"""

    capability = SourceCapability(
        source_id="sina",
        markets=(Market.CN.value,),
        credential_required=False,
        supports_realtime=True,
    )

    def __init__(self, http_get: Callable[[str], bytes]) -> None:
        """保存受控 HTTP GET 读取器，适配器自身不创建网络连接。"""

        self._http_get = http_get

    def fetch_quotes(self, codes: list[str], collected_at: datetime) -> list[NormalizedQuote]:
        """读取全部请求代码；任一异常均拒绝返回部分行情。"""

        self._validate_codes(codes)
        url = f"{_SINA_URL_PREFIX}{','.join(codes)}"
        try:
            raw_response = self._http_get(url)
            if not isinstance(raw_response, bytes):
                raise TypeError("HTTP 读取器必须返回字节串")
            decoded_response = raw_response.decode("gbk")
            parsed_fields = self._parse_response(decoded_response, codes)
            data_version = f"sina-{hashlib.sha256(raw_response).hexdigest()}"
            return [
                self._normalize_quote(code, parsed_fields[code], collected_at, data_version)
                for code in codes
            ]
        except SinaDataSourceError:
            raise
        except Exception as error:
            raise SinaDataSourceError("新浪行情响应无效，拒绝生成量化行情") from error

    @staticmethod
    def _validate_codes(codes: list[str]) -> None:
        if not codes or any(_SINA_CODE_PATTERN.fullmatch(code) is None for code in codes):
            raise SinaDataSourceError("新浪请求代码必须为 sh 或 sz 加六位 ASCII 数字")
        if len(set(codes)) != len(codes):
            raise SinaDataSourceError("新浪请求代码不能重复")

    @staticmethod
    def _parse_response(response: str, codes: list[str]) -> dict[str, list[str]]:
        if not response.strip():
            raise SinaDataSourceError("新浪响应不能为空")

        parsed: dict[str, list[str]] = {}
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        for line in lines:
            match = _SINA_LINE_PATTERN.fullmatch(line)
            if match is None:
                raise SinaDataSourceError("新浪响应格式错误")
            code = match.group("code")
            if code not in codes or code in parsed:
                raise SinaDataSourceError("新浪响应包含未请求或重复的证券代码")
            fields = match.group("fields").split(",")
            if len(fields) <= 31 or not fields[0].strip():
                raise SinaDataSourceError("新浪响应缺少证券名称或关键字段")
            parsed[code] = fields

        if set(parsed) != set(codes):
            raise SinaDataSourceError("新浪响应缺少请求的证券行情")
        return parsed

    @staticmethod
    def _normalize_quote(
        code: str,
        fields: list[str],
        collected_at: datetime,
        data_version: str,
    ) -> NormalizedQuote:
        try:
            price = float(fields[3])
            if not math.isfinite(price):
                raise ValueError("价格必须为有限数值")
            market_time = datetime.strptime(
                f"{fields[30].strip()} {fields[31].strip()}", "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=_SHANGHAI_TIMEZONE)
            freshness_state = classify_freshness(Market.CN, market_time, collected_at, is_open=True)
            age_seconds = int((collected_at - market_time).total_seconds())
            match = _SINA_CODE_PATTERN.fullmatch(code)
            if match is None:
                raise ValueError("响应代码格式错误")
            exchange = "SSE" if match.group("prefix") == "sh" else "SZSE"
            return NormalizedQuote(
                security_id=InstrumentIdentity(
                    market=Market.CN,
                    exchange=exchange,
                    display_code=match.group("display_code"),
                    currency="CNY",
                ),
                price=price,
                source_id="sina",
                market_time=market_time,
                collected_at=collected_at,
                data_version=data_version,
                freshness=Freshness(state=freshness_state, age_seconds=age_seconds),
            )
        except Exception as error:
            raise SinaDataSourceError("新浪响应包含无法使用的价格或市场时间") from error
