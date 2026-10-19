"""App local: entradas, revisão humana e inspector sem base64."""
import atexit
import json
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_from_directory
from openai import OpenAIError
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import HTTPException

from config import DATA, MAX_BYTES, PORT, ROOT, RUNTIME, configured_model
from exercises import EXERCISES
from media import prepare_media
from store import load_data
from workflow import open_workflow


def create_app(runtime_dir: Path = RUNTIME) -> Flask:
    app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
    app.config["MAX_CONTENT_LENGTH"] = 4 * MAX_BYTES + 100_000
    context = open_workflow(runtime_dir)
    runtime = context.__enter__()
    atexit.register(context.__exit__, None, None, None)
    app.extensions["aula_runtime"] = runtime
    app.extensions["aula_context"] = context
    media_dir = Path(runtime_dir) / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    def public_state(state):
        # Apenas URLs sob a pasta de mídia local; caminhos não chegam à interface.
        result = json.loads(json.dumps(state))
        def public_item(item):
            item = dict(item)
            item["url"] = "/media/runtime/" + Path(item.pop("path")).relative_to(media_dir).as_posix()
            return item
        result["evidence"] = [public_item(e) for e in result["evidence"]]
        result["proposal"].pop("evidence", None)
        bundle = media_dir / result["cycle"] / "originals.json"
        result["originals"] = [public_item(e) for e in json.loads(bundle.read_text(encoding="utf-8"))] if bundle.exists() else []
        return result

    @app.before_request
    def same_origin():
        if request.method == "POST" and request.headers.get("Origin"):
            if request.headers["Origin"] != request.host_url.rstrip("/"):
                raise ValueError("Origem da requisição não permitida.")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/meta")
    def meta():
        return jsonify(model=configured_model(), case=load_data("case.json"), policy=load_data("policy.json"),
                       kit=load_data("media_manifest.json")["files"], exercises=EXERCISES)

    @app.get("/api/cases")
    def cases():
        return jsonify([{"thread": p["proposal_id"], "version": p["version"], "status": p["status"]}
                        for p in runtime.store.list_proposals()])

    @app.get("/api/cases/<thread>")
    def get_case(thread):
        return jsonify(public_state(runtime.snapshot(thread)))

    @app.post("/api/analyze")
    def analyze():
        mode = request.form.get("mode", "provided")
        frame_count = int(request.form.get("frames", "8"))
        selected = json.loads(request.form.get("kit", "[]"))
        uploads = request.files.getlist("files")
        if not isinstance(selected, list) or len(selected) + len(uploads) > 4:
            raise ValueError("Selecione até quatro mídias por análise.")
        allowed = {item["file"] for item in load_data("media_manifest.json")["files"]}
        if any(not isinstance(name, str) or name not in allowed for name in selected):
            raise ValueError("Item do kit desconhecido.")
        batch = uuid4().hex
        directory = media_dir / batch
        directory.mkdir()
        paths = [DATA / "media" / name for name in selected]
        for index, upload in enumerate(uploads):
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".mp4"}:
                raise ValueError("Formato não permitido.")
            target = directory / f"upload_{index}{suffix}"
            upload.save(target)
            if target.stat().st_size > MAX_BYTES:
                raise ValueError("Cada upload deve ter até 10 MB.")
            paths.append(target)
        evidence, originals = prepare_media(paths, directory, frame_count)
        thread = request.form.get("thread") or None
        state = runtime.start(request.form.get("message", ""), evidence, mode,
                              request.form.get("fixture", "clear"), thread)
        # Liga o manifesto de previews ao ciclo persistido, inclusive após restart.
        manifest = media_dir / state["cycle"]
        manifest.mkdir(exist_ok=True)
        (manifest / "originals.json").write_text(json.dumps(originals), encoding="utf-8")
        return jsonify(public_state(state))

    @app.post("/api/cases/<thread>/decision")
    def decision(thread):
        return jsonify(public_state(runtime.resume(thread, request.get_json())))

    @app.get("/media/runtime/<path:name>")
    def media(name):
        if Path(name).suffix.lower() not in {".jpg", ".mp4"}:
            raise ValueError("Arquivo não disponível para preview.")
        return send_from_directory(media_dir, name)

    @app.get("/media/kit/<name>")
    def kit_media(name):
        allowed = {item["file"] for item in load_data("media_manifest.json")["files"]}
        if name not in allowed:
            raise ValueError("Mídia desconhecida.")
        return send_from_directory(DATA / "media", name)

    @app.errorhandler(ValueError)
    @app.errorhandler(UnidentifiedImageError)
    @app.errorhandler(Image.DecompressionBombError)
    def bad_request(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(OpenAIError)
    def api_error(error):
        # Não refletir headers, chaves, payloads ou detalhes do SDK no browser.
        return jsonify(error=f"Falha de API ({type(error).__name__}). Nenhuma análise fornecida foi usada como fallback."), 502

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=PORT, debug=False)
