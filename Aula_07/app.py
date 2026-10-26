"""Servidor local da aula: UI, stream de eventos e retomada da revisão."""
import base64
import hashlib
import json
import sqlite3
from pathlib import Path
from threading import RLock
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_from_directory, stream_with_context
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env", override=False)

import lesson
import memory
from workflow import build_graph

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
memory.RUNTIME.mkdir(exist_ok=True)
connection = sqlite3.connect(memory.RUNTIME / "checkpoints.sqlite3", check_same_thread=False)
graph = build_graph(SqliteSaver(connection))
lock = RLock()  # Uma execução por vez simplifica o laboratório local.
VERSION = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(ROOT.glob("*.py")))).hexdigest()[:8]


def config(run_id):
    return {"configurable": {"thread_id": str(run_id)}, "recursion_limit": 50}


def public_state(run_id):
    snapshot = graph.get_state(config(run_id))
    state = snapshot.values
    if not state:
        raise ValueError("Execução não encontrada.")
    plan = state.get("plan", {})
    total = round(sum(c["quantity"] * c["unit_price"] for c in plan.get("costs", [])), 2) if plan.get("costs") else None
    status = ("pending" if snapshot.next == ("review",) else "saved" if state.get("receipt") else
              "rejected" if state.get("decision", {}).get("action") == "reject" else "draft")
    return {"id": state["id"], "session": state["session"], "message": state["message"],
            "settings": state["settings"], "plan": plan, "total": total, "status": status,
            "revision": state.get("revision", 1), "receipt": state.get("receipt"),
            "events": state.get("events", []), "catalog": state.get("catalog", {}),
            "agents": state.get("agents", {}), "visual": state.get("visual", ""),
            "sources": list({d["id"]: d for d in state.get("evidence", [])}.values()),
            "memory": {"history": state.get("history", []), "preference": state.get("preference", "")}}


def streaming(value, run_id, expected_revision=None):
    def line(kind, data):
        return json.dumps({"type": kind, "data": data}, ensure_ascii=False, default=str) + "\n"

    @stream_with_context
    def generate():
        with lock:
            try:
                if expected_revision is not None:
                    pending = public_state(run_id)
                    if pending["status"] != "pending" or pending["revision"] != expected_revision:
                        raise ValueError("A revisão mudou. Atualize a página antes de decidir.")
                yield line("started", {"id": str(run_id), "version": VERSION, "settings": lesson.settings()})
                for event in graph.stream(value, config(run_id), stream_mode="custom"):
                    yield line("event", event)
                yield line("result", public_state(run_id))
            except Exception as error:
                app.logger.exception("Falha na execução %s", run_id)
                yield line("error", {"message": str(error)})
    return Response(generate(), mimetype="application/x-ndjson", headers={"Cache-Control": "no-store"})


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/meta")
def meta():
    return jsonify(settings=lesson.settings(), version=VERSION, model=lesson.model_name(), default_request=lesson.DEFAULT_REQUEST)


@app.get("/dados/sala.png")
def room():
    return send_from_directory(ROOT / "dados", "sala.png")


@app.post("/api/run")
def run():
    body = request.get_json()
    message = body.get("message", "").strip()
    if not message:
        return jsonify(error="Escreva um pedido."), 400
    image = body.get("image", "") if lesson.USE_IMAGE else ""
    if image == "kit":
        image = "data:image/png;base64," + base64.b64encode((ROOT / "dados" / "sala.png").read_bytes()).decode()
    if image and not image.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")):
        return jsonify(error="Use uma imagem PNG, JPEG ou WEBP."), 400
    run_id = str(uuid4())
    state = {"id": run_id, "session": body.get("session") or str(uuid4()), "message": message,
             "image": image, "settings": lesson.settings(), "events": [], "evidence": []}
    # Repetir preserva o contexto inicial, evitando que a memória confunda a comparação.
    if body.get("replay_of"):
        previous = graph.get_state(config(body["replay_of"])).values
        if previous and previous["session"] == state["session"] and previous["message"] == message:
            state["replay"] = {"history": previous.get("history", []), "preference": previous.get("preference", "")}
    return streaming(state, run_id)


@app.get("/api/runs/<uuid:run_id>")
def recover(run_id):
    try:
        return jsonify(public_state(run_id))
    except ValueError as error:
        return jsonify(error=str(error)), 404


@app.post("/api/review/<uuid:run_id>")
def review(run_id):
    decision = request.get_json()
    with lock:
        state = public_state(run_id)
        if state["status"] != "pending" or decision.get("revision") != state["revision"]:
            return jsonify(error="Esta revisão não está pendente. Recupere a execução atual."), 409
        if decision.get("action") not in {"approve", "reject", "edit"}:
            return jsonify(error="Decisão inválida."), 400
    # Expansão: autenticar o revisor nesta fronteira, antes de retomar.
    return streaming(Command(resume=decision), run_id, decision["revision"])


@app.get("/api/memory/<session>")
def inspect_memory(session):
    return jsonify(memory.read(session))


@app.post("/api/preference")
def preference():
    value = request.get_json().get("value", "").strip()
    memory.save_preference(value)
    return jsonify(preference=value)


if __name__ == "__main__":
    # O reloader observa os módulos importados; não é necessário redeploy local.
    app.run(host="127.0.0.1", port=5004, debug=True, use_debugger=False)
