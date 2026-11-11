"""Record real provider responses once, replay them offline.

A cassette is keyed by a hash of everything that shapes the request (model, prompt,
schema, limits). Change a prompt or the model and the key changes: replay then
reports a miss instead of silently scoring stale output.
Replayed usage is the usage the provider reported when the cassette was recorded.
Cassettes store responses only: no headers, no credentials.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from mindmap.errors import ProviderError
from mindmap.llm.base import LLMProvider, LLMRequest, LLMResponse, Usage


class CassetteMissing(ProviderError):
    retryable = False


def request_key(request: LLMRequest) -> str:
    material = {
        "model": request.model,
        "system": request.system,
        "messages": request.messages,
        "schema": request.schema,
        "max_tokens": request.max_tokens,
        "effort": request.effort,
    }
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


class RecordingProvider:
    name = "record"

    def __init__(self, inner: LLMProvider, directory: Path) -> None:
        self.inner = inner
        self.directory = directory

    def complete(self, request: LLMRequest) -> LLMResponse:
        response = self.inner.complete(request)
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "key": request_key(request),
            "purpose": request.purpose,
            "attempt": request.attempt,
            "requested_model": request.model,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "response": {
                "text": response.text,
                "stop_reason": response.stop_reason,
                "model": response.model,
                "provider": response.provider,
                "request_id": response.request_id,
                "usage": response.usage.__dict__,
            },
        }
        path = self.directory / f"{payload['key']}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return response


class ReplayProvider:
    name = "replay"

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def complete(self, request: LLMRequest) -> LLMResponse:
        path = self.directory / f"{request_key(request)}.json"
        if not path.is_file():
            raise CassetteMissing(f"no recorded response for this request ({path.name}); re-record in live mode")
        data = json.loads(path.read_text(encoding="utf-8"))["response"]
        return LLMResponse(
            text=data["text"],
            stop_reason=data["stop_reason"],
            model=data["model"],
            usage=Usage(**data["usage"]),
            provider=f"replay:{data['provider']}",
            request_id=data.get("request_id"),
        )
