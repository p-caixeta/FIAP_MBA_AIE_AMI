"""Host Flask local para a Aula 05: grafo, memória e cliente MCP."""

from __future__ import annotations

import queue
import threading
import asyncio
import json
from pathlib import Path
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
from memory import new_thread, load_thread, read_profile, save_profile, revoke_profile
from tool_gateway import INTEGRATIONS, TRANSPORTS
from diagnostics import diagnose


load_environment()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32_768
EXERCISES = json.loads((Path(__file__).parent / "exercises.json").read_text(encoding="utf-8"))

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
    stage = request.args.get("stage", "fixed_rag")
    if not isinstance(stage, str) or stage not in STAGES:
        return error_response("invalid_stage", "Etapa inválida.", 400)
    return jsonify(
        {
            "version": "aula05-v0.1",
            "build_id": build_id(),
            "key_configured": key_configured(),
            "model": configured_model(),
            "stage": stage,
            "graph": graph_description(stage),
            "examples": EXAMPLES,
            "exercises": EXERCISES,
            "integrations": sorted(INTEGRATIONS),
            "transports": sorted(TRANSPORTS),
        }
    )


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("invalid_json", "Envie um objeto JSON.", 400)
    message = payload.get("message")
    stage = payload.get("stage", "fixed_rag")
    if not isinstance(stage, str) or stage not in STAGES:
        return error_response("invalid_stage", "Etapa inválida.", 400)
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE_CHARS:
        return error_response("invalid_message", "A pergunta deve ter entre 1 e 4000 caracteres.", 400)
    integration = payload.get("integration", "mcp_tools_rag")
    transport = payload.get("transport", "stdio")
    if not isinstance(integration, str) or integration not in INTEGRATIONS or not isinstance(transport, str) or transport not in TRANSPORTS:
        return error_response("invalid_integration", "Integração ou transporte inválido.", 400)
    mode = payload.get("memory_mode", "shared")
    strategy = payload.get("strategy", "structured")
    thread_id = payload.get("thread_id")
    if not isinstance(mode, str) or mode not in ("off", "short", "long", "shared"):
        return error_response("invalid_mode", "Modo de memória inválido.", 400)
    if not isinstance(strategy, str) or strategy not in ("none", "recent", "structured"):
        return error_response("invalid_strategy", "Estratégia inválida.", 400)
    try:
        if mode != "off":
            if not isinstance(thread_id, str):
                raise ValueError("Crie uma conversa antes de enviar.")
            load_thread(thread_id)
    except ValueError as error:
        return error_response("invalid_thread", str(error), 400)
    if not key_configured():
        return error_response("missing_api_key", "Crie .env com OPENAI_API_KEY e reinicie o servidor.", 503)

    event_queue: queue.Queue = queue.Queue()
    sentinel = object()
    _, emit = make_emitter(sink=event_queue.put)

    def worker():
        try:
            run_case(message.strip(), stage=stage, emit=emit, thread_id=thread_id,
                     memory_mode=mode, strategy=strategy, integration=integration, transport=transport)
        except Exception as error:
            emit("run_error", code="execution_failed", message=_public_error(error))
        finally:
            event_queue.put(sentinel)

    thread = threading.Thread(target=worker, daemon=True, name="aula05-run")
    thread.start()

    def stream():
        while True:
            item = event_queue.get()
            if item is sentinel:
                break
            yield ndjson_line(item)

    return Response(stream(), content_type="application/x-ndjson; charset=utf-8", headers={"Cache-Control": "no-store"})


@app.post("/api/mcp/diagnostic")
def mcp_diagnostic():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("invalid_json", "Envie um objeto JSON.", 400)
    action, transport = payload.get("action", "discover"), payload.get("transport", "stdio")
    if not isinstance(action, str) or action not in ("discover", "call", "resource", "compare", "timeout"):
        return error_response("invalid_action", "Ação inválida.", 400)
    if not isinstance(transport, str) or transport not in TRANSPORTS:
        return error_response("invalid_transport", "Transporte inválido.", 400)
    name, arguments = payload.get("name", "get_order"), payload.get("arguments", {})
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return error_response("invalid_arguments", "Nome e argumentos inválidos.", 400)
    from events import collect_events
    events, emit = collect_events()
    result = asyncio.run(diagnose(action, transport, name, arguments, emit))
    return jsonify({"result": result, "events": events})


@app.post("/api/threads")
def create_thread():
    return jsonify({"thread_id": new_thread()})


@app.get("/api/threads/<thread_id>")
def inspect_thread(thread_id):
    try:
        return jsonify(load_thread(thread_id))
    except ValueError as error:
        return error_response("invalid_thread", str(error), 404)


@app.route("/api/profile", methods=["GET", "POST", "DELETE"])
def profile():
    if request.method == "GET":
        return jsonify(read_profile())
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict) or type(data.get("version")) is not int:
        return error_response("invalid_profile", "Informe a versão lida do perfil.", 400)
    try:
        if request.method == "DELETE":
            return jsonify(revoke_profile(data["version"]))
        return jsonify(save_profile(data.get("value"), data.get("confirmed"), data["version"]))
    except ValueError as error:
        return error_response("profile_update_failed", str(error), 409)


def _public_error(error: Exception) -> str:
    text = str(error).casefold()
    if "context_budget_exceeded" in text:
        return "Contexto excedeu o orçamento didático. Reduza a seleção em context.py e repita."
    if "memory_conflict" in text:
        return "Outra execução atualizou a conversa. Recarregue o estado e repita."
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
