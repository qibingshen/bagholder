"""提供只读新浪 A 股行情 HTTP 适配器。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from stock_agent.adapters.market_data.base import NormalizedQuote, SourceCapability
from stock_agent.application.versioning_service import VersioningService
from stock_agent.contracts.common import Freshness
from stock_agent.domain.freshness import calculate_age_seconds, classify_freshness
from stock_agent.domain.market import InstrumentIdentity, Market

_SINA_URL_PREFIX = "http://hq.sinajs.cn/list="
_SINA_CODE_PATTERN = re.compile(r"(?P<prefix>sh|sz)(?P<display_code>[0-9]{6})\Z")
_SINA_LINE_PATTERN = re.compile(
    r'var hq_str_(?P<code>sh[0-9]{6}|sz[0-9]{6})="(?P<fields>[^"]*)";\Z'
)
_SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")


class SinaDataSourceError(RuntimeError):
    """表示新浪读取结果无法安全转换为完整规范化行情。"""


@dataclass(frozen=True, slots=True)
class SinaPersistenceProof:
    """描述已追加提交的原始和规范化行情工件及其版本关联。"""

    raw_artifact_version_id: str
    normalized_artifact_version_id: str
    parent_version_id: str


class SinaFactRecorder(Protocol):
    """定义新浪行情事实记录端口，适配器不直接依赖具体本地实现。"""

    def record(self, raw_response: bytes, normalized_content: bytes) -> SinaPersistenceProof:
        """追加保存适配器生成的原始响应与规范化批次，并返回工件关联。"""


class SinaHttpAdapter:
    """通过调用方注入的读取器获取并验证新浪 A 股实时报价。"""

    capability = SourceCapability(
        source_id="sina",
        markets=(Market.CN.value,),
        credential_required=False,
        supports_realtime=True,
    )

    def __init__(
        self,
        http_get: Callable[[str], bytes],
        fact_recorder: SinaFactRecorder,
        versioning_service: VersioningService,
    ) -> None:
        """绑定读取器、记录器和既有版本服务，拒绝无真实工件验证的读取路径。"""

        self._http_get = http_get
        self._fact_recorder = fact_recorder
        self._versioning_service = versioning_service

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
            quotes = [
                self._normalize_quote(code, parsed_fields[code], collected_at, data_version)
                for code in codes
            ]
            normalized_content = self._serialize_normalized_batch(quotes)
            normalized_content_hash = hashlib.sha256(normalized_content).hexdigest()
            proof = self._fact_recorder.record(raw_response, normalized_content)
            self._validate_persistence_proof(proof)
            self._verify_persisted_artifacts(proof, raw_response, normalized_content_hash)
            return quotes
        except SinaDataSourceError:
            raise
        except Exception as error:
            raise SinaDataSourceError("新浪行情响应或本地事实保存无效，拒绝生成量化行情") from error

    @staticmethod
    def _validate_persistence_proof(proof: SinaPersistenceProof) -> None:
        """确认记录器返回了完整的原始、规范化工件与父版本关联证明。"""

        if not isinstance(proof, SinaPersistenceProof):
            raise SinaDataSourceError("新浪事实保存未返回可验证的持久化证明")
        if (
            not proof.raw_artifact_version_id
            or not proof.normalized_artifact_version_id
            or proof.parent_version_id != proof.raw_artifact_version_id
        ):
            raise SinaDataSourceError("新浪事实保存返回的持久化证明不完整")

    def _verify_persisted_artifacts(
        self,
        proof: SinaPersistenceProof,
        raw_response: bytes,
        normalized_content_hash: str,
    ) -> None:
        """从既有版本服务回读工件和元数据，拒绝仅形态正确的伪造证明。"""

        raw_dataset = "market-data-raw"
        normalized_dataset = "market-data-normalized"
        if not (
            self._versioning_service.version_exists(raw_dataset, proof.raw_artifact_version_id)
            and self._versioning_service.version_exists(
                normalized_dataset, proof.normalized_artifact_version_id
            )
        ):
            raise SinaDataSourceError("新浪事实工件未实际落盘")

        raw_content = self._versioning_service.read_bytes(
            raw_dataset, proof.raw_artifact_version_id
        )
        normalized_content = self._versioning_service.read_bytes(
            normalized_dataset, proof.normalized_artifact_version_id
        )
        normalized_metadata = self._versioning_service.metadata_for(
            normalized_dataset, proof.normalized_artifact_version_id
        )
        if (
            hashlib.sha256(raw_content).hexdigest() != hashlib.sha256(raw_response).hexdigest()
            or hashlib.sha256(normalized_content).hexdigest() != normalized_content_hash
            or normalized_metadata["parent_version_id"] != proof.raw_artifact_version_id
        ):
            raise SinaDataSourceError("新浪事实工件与当前规范化报价批次或父版本关联不匹配")

    @staticmethod
    def _serialize_normalized_batch(quotes: Sequence[NormalizedQuote]) -> bytes:
        """确定性序列化当前返回的完整报价批次，作为回读校验的唯一事实载荷。"""

        if not quotes:
            raise SinaDataSourceError("新浪规范化报价批次不能为空")
        first = quotes[0]
        if any(
            quote.source_id != first.source_id or quote.data_version != first.data_version
            for quote in quotes
        ):
            raise SinaDataSourceError("新浪规范化报价批次的来源或数据版本不一致")
        return json.dumps(
            {
                "data_version": first.data_version,
                "quotes": [quote.model_dump(mode="json") for quote in quotes],
                "source_id": first.source_id,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

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
            age_seconds = calculate_age_seconds(market_time, collected_at)
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
