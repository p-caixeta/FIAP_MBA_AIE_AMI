"""Servidor Flask local para a Aula 03."""

from __future__ import annotations

import queue
import threading
from copy import deepcopy

from flask import Flask, Response, jsonify, render_template, request

from config import (
    HOST,
    MAX_HISTORY_MESSAGES,
    MAX_MESSAGE_CHARS,
    PORT,
    build_id,
    configured_model,
    key_configured,
    load_environment,
)
from events import make_emitter, ndjson_line
from graph import STAGES, graph_description, run_case


load_environment()
app = Flask(__name__)

EXAMPLES = [
    "Meu pedido P100 está atrasado. O que aconteceu?",
    "P100 atrasou e não há previsão; o que podemos fazer?",
    "Qual fila de exceção para P400 expresso_demo?",
]


def error_response(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def normalize_history(value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_HISTORY_MESSAGES:
        raise ValueError("O histórico deve ter no máximo oito mensagens.")
    clean = []
    for item in value:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            raise ValueError("O histórico aceita somente mensagens user/assistant.")
        content = item.get("content")
        if not isinstance(content, str) or len(content) > MAX_MESSAGE_CHARS:
            raise ValueError("Uma mensagem do histórico é inválida ou longa demais.")
        clean.append({"role": item["role"], "content": content})
    return clean


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/meta")
def meta():
    stage = request.args.get("stage", "baseline")
    if not isinstance(stage, str) or stage not in STAGES:
        return error_response("invalid_stage", "Etapa inválida.", 400)
    return jsonify(
        {
            "version": "v0.1",
            "build_id": build_id(),
            "key_configured": key_configured(),
            "model": configured_model(),
            "stage": stage,
            "graph": graph_description(stage),
            "examples": EXAMPLES,
        }
    )


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("invalid_json", "Envie um objeto JSON.", 400)
    message = payload.get("message")
    stage = payload.get("stage", "baseline")
    if not isinstance(stage, str) or stage not in STAGES:
        return error_response("invalid_stage", "Etapa inválida.", 400)
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE_CHARS:
        return error_response("invalid_message", "A pergunta deve ter entre 1 e 4000 caracteres.", 400)
    try:
        history = normalize_history(payload.get("history", []))
    except ValueError as error:
        return error_response("invalid_history", str(error), 400)
    if not key_configured():
        return error_response("missing_api_key", "Crie .env com OPENAI_API_KEY e reinicie o servidor.", 503)

    event_queue: queue.Queue = queue.Queue()
    sentinel = object()
    _, emit = make_emitter(sink=event_queue.put)

    def worker():
        try:
            run_case(message.strip(), stage=stage, history=deepcopy(history), emit=emit)
        except Exception as error:
            emit("run_error", code="execution_failed", message=_public_error(error))
        finally:
            event_queue.put(sentinel)

    thread = threading.Thread(target=worker, daemon=True, name="aula03-run")
    thread.start()

    def stream():
        while True:
            item = event_queue.get()
            if item is sentinel:
                break
            yield ndjson_line(item)

    return Response(stream(), content_type="application/x-ndjson; charset=utf-8", headers={"Cache-Control": "no-store"})


def _public_error(error: Exception) -> str:
    text = str(error).casefold()
    if "auth" in text or "api key" in text or "401" in text:
        return "Não foi possível autenticar a chave do modelo."
    if "quota" in text or "429" in text:
        return "A cota do modelo foi atingida."
    if "timeout" in text:
        return "A chamada ao modelo excedeu o tempo limite."
    if "404" in text or "model_not_found" in text:
        return "Modelo não encontrado. Verifique OPENAI_MODEL e o acesso da chave."
    if "connection" in text or "connect" in text:
        return "Não foi possível conectar ao serviço do modelo. Verifique a rede."
    return "A execução foi interrompida. Verifique a conexão e a configuração do modelo."


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, threaded=True, debug=True, use_reloader=True, use_debugger=False)
