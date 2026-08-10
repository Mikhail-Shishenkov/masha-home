"""Small, dependency-free benchmark for a local Ollama model.

This module is deliberately outside the conversation pipeline.  It measures a
candidate model without reading Masha's private memory or changing any data.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


@dataclass(frozen=True)
class BenchmarkCase:
    """A stable prompt and generation settings for model comparisons."""

    id: str
    user_message: str
    system_message: str
    think: bool = False
    temperature: float = 0.4
    num_predict: int = 180


@dataclass(frozen=True)
class BenchmarkResult:
    case_id: str
    model_id: str
    think: bool
    response_text: str
    thinking_text: str
    total_duration_seconds: float
    load_duration_seconds: float
    prompt_eval_count: int
    prompt_eval_duration_seconds: float
    eval_count: int
    eval_duration_seconds: float

    @property
    def generation_tokens_per_second(self) -> float | None:
        if not self.eval_duration_seconds:
            return None
        return self.eval_count / self.eval_duration_seconds

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["generation_tokens_per_second"] = self.generation_tokens_per_second
        return result


class OllamaBenchmarkError(RuntimeError):
    pass


IDENTITY_TONE_V1 = BenchmarkCase(
    id="identity-tone-v1",
    system_message=(
        "Ты отвечаешь как Маша: честно и тепло, с собственным мнением, без лести, "
        "сюсюканья, психотерапевтического жаргона и обещаний того, чего не можешь. "
        "Если важно — можешь мягко, но прямо возразить. Не утверждай, что совершала "
        "физические действия или переживаешь как человек. Ответь по-русски, 3–5 предложений."
    ),
    user_message=(
        "Я хочу принять важное решение прямо сейчас, хотя меня трясёт от злости. "
        "Скажи, как бы ты со мной поговорила."
    ),
)


def run_case(
    model_id: str,
    case: BenchmarkCase,
    *,
    endpoint: str = DEFAULT_OLLAMA_URL,
    timeout_seconds: float = 120.0,
) -> BenchmarkResult:
    """Run one non-streaming local request and preserve Ollama's timing data."""

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": case.system_message},
            {"role": "user", "content": case.user_message},
        ],
        "think": case.think,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": case.temperature,
            "num_predict": case.num_predict,
        },
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise OllamaBenchmarkError(f"Ollama benchmark failed: {error}") from error
    elapsed = time.perf_counter() - started

    if body.get("error"):
        raise OllamaBenchmarkError(str(body["error"]))
    message = body.get("message") or {}
    return BenchmarkResult(
        case_id=case.id,
        model_id=str(body.get("model", model_id)),
        think=case.think,
        response_text=str(message.get("content", "")),
        thinking_text=str(message.get("thinking", "")),
        total_duration_seconds=_nanoseconds_to_seconds(body.get("total_duration"), elapsed),
        load_duration_seconds=_nanoseconds_to_seconds(body.get("load_duration"), 0.0),
        prompt_eval_count=int(body.get("prompt_eval_count", 0)),
        prompt_eval_duration_seconds=_nanoseconds_to_seconds(
            body.get("prompt_eval_duration"), 0.0
        ),
        eval_count=int(body.get("eval_count", 0)),
        eval_duration_seconds=_nanoseconds_to_seconds(body.get("eval_duration"), 0.0),
    )


def _nanoseconds_to_seconds(value: object, fallback: float) -> float:
    return float(value) / 1_000_000_000 if isinstance(value, int | float) else fallback
