"""Configuração pequena e explícita da aplicação local."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 5000
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
AS_OF = "2026-09-01"
TENANT_ID = "loja_demo"
TOP_K = 3
MAX_TOP_K = 5
MAX_SEARCHES = 2
MAX_EVIDENCE_CHUNKS = 6
MAX_MESSAGE_CHARS = 4_000
MAX_HISTORY_MESSAGES = 8
MODEL_TIMEOUT_S = 30
RUN_DEADLINE_S = 120


def load_environment() -> None:
    """Carrega somente o .env local do servidor, sem sobrescrever o ambiente."""
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)


def key_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def configured_model() -> str:
    return os.getenv("OPENAI_MODEL", MODEL).strip() or MODEL


def _compute_build_id() -> str:
    """Identifica o código e os dados carregados, sem incluir o .env."""
    names = [
        "config.py", "events.py", "tools.py", "retrieval.py", "agents.py", "graph.py",
        "dados/corpus_manifest.json", "dados/chunks.json", "dados/orders.json", "dados/shipments.json",
    ]
    digest = hashlib.sha256()
    for relative in names:
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


_BUILD_ID = _compute_build_id()


def build_id() -> str:
    """Identifica a versão carregada pelo processo, até o próximo reload."""
    return _BUILD_ID
