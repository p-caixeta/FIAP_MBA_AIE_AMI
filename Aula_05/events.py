"""Eventos JSON seguros, ordenados por execução e reutilizáveis nos notebooks."""

from __future__ import annotations

import json
import threading
import time
import uuid
from copy import deepcopy
from typing import Any, Callable


def json_safe(value: Any) -> Any:
    """Converte dados observáveis em tipos aceitos por json.dumps."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "model_dump"):
        return json_safe(value.model_dump())
    return str(value)


def make_emitter(run_id: str | None = None, sink: Callable[[dict], None] | None = None):
    """Cria um emissor isolado. ``sink`` recebe um evento completo por chamada."""
    resolved_run_id = run_id or str(uuid.uuid4())
    started_at = time.perf_counter()
    lock = threading.Lock()
    sequence = 0

    def emit(event_type: str, **data: Any) -> dict:
        nonlocal sequence
        with lock:
            sequence += 1
            event = {
                "run_id": resolved_run_id,
                "seq": sequence,
                "type": event_type,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
                "data": json_safe(deepcopy(data)),
            }
            if sink:
                sink(event)
            return event

    return resolved_run_id, emit


def collect_events() -> tuple[list[dict], Callable[[str], dict]]:
    """Adaptador simples de notebook: mantém a mesma forma de evento sem Flask."""
    items: list[dict] = []
    _, emit = make_emitter(sink=items.append)
    return items, emit


def ndjson_line(event: dict) -> str:
    return json.dumps(json_safe(event), ensure_ascii=False) + "\n"
