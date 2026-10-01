"""Memória didática: conversas e preferências em SQLite, sem serviço externo.

Salvamos turnos concluídos, não checkpoints de execução do LangGraph.
Cada chamada abre/fecha sua conexão. O banco nunca é distribuído com o exemplo.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "runtime" / "memory.sqlite3"


def utc_now():
    return datetime.now(timezone.utc)


@contextmanager
def connect(db_path=None):
    path = Path(db_path or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, user_id TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS turns (
                    thread_id TEXT NOT NULL, number INTEGER NOT NULL, content TEXT NOT NULL,
                    PRIMARY KEY(thread_id, number));
                CREATE TABLE IF NOT EXISTS profiles (
                    tenant TEXT NOT NULL, user_id TEXT NOT NULL, version INTEGER NOT NULL,
                    value TEXT NOT NULL, source TEXT NOT NULL, expires_at TEXT NOT NULL,
                    active INTEGER NOT NULL, PRIMARY KEY(tenant, user_id));
            """)
            yield connection
    finally:
        connection.close()


def new_thread(tenant="loja_demo", user_id="U100", db_path=None):
    thread_id = str(uuid.uuid4())
    with connect(db_path) as conn:
        conn.execute("INSERT INTO threads(id, tenant, user_id, state) VALUES(?,?,?,?)",
                     (thread_id, tenant, user_id, "{}"))
    return thread_id


def _owned_thread(conn, thread_id, tenant, user_id):
    row = conn.execute("SELECT * FROM threads WHERE id=? AND tenant=? AND user_id=?",
                       (thread_id, tenant, user_id)).fetchone()
    if row is None:
        raise ValueError("thread_not_found_or_not_owned")
    return row


def load_thread(thread_id, tenant="loja_demo", user_id="U100", db_path=None):
    with connect(db_path) as conn:
        row = _owned_thread(conn, thread_id, tenant, user_id)
        turns = conn.execute("SELECT content FROM turns WHERE thread_id=? ORDER BY number",
                             (thread_id,)).fetchall()
        return {"thread_id": thread_id, "version": row["version"],
                "state": json.loads(row["state"]), "turns": [json.loads(t[0]) for t in turns]}


def save_turn(thread_id, expected_version, state, turn, tenant="loja_demo", user_id="U100", db_path=None):
    """Compare-and-swap: um segundo resultado obsoleto não apaga o primeiro."""
    with connect(db_path) as conn:
        _owned_thread(conn, thread_id, tenant, user_id)
        updated = conn.execute("UPDATE threads SET state=?, version=version+1 WHERE id=? AND version=?",
                               (json.dumps(state, ensure_ascii=False), thread_id, expected_version))
        if updated.rowcount != 1:
            raise ValueError("memory_conflict: recarregue a conversa")
        conn.execute("INSERT INTO turns VALUES(?,?,?)",
                     (thread_id, expected_version + 1, json.dumps(turn, ensure_ascii=False)))
    return expected_version + 1


def read_profile(tenant="loja_demo", user_id="U100", db_path=None, now=None):
    """Lookup por identidade antes de retornar qualquer conteúdo; não copia outra thread."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM profiles WHERE tenant=? AND user_id=?",
                           (tenant, user_id)).fetchone()
    if not row:
        return {"version": 0, "active": False}
    profile = dict(row)
    profile["active"] = bool(profile["active"] and profile["expires_at"] > (now or utc_now()).isoformat())
    if not profile["active"]:
        profile.pop("value", None)
        profile.pop("source", None)
    return profile


def save_profile(value, confirmed, expected_version, tenant="loja_demo", user_id="U100", db_path=None, now=None):
    """Exercício 2.1/2.2: guardar só formato confirmado, corrigir com versão."""
    if confirmed is not True or value not in ("concise", "detailed"):
        raise ValueError("confirmed_preference_required")
    expires = ((now or utc_now()) + timedelta(days=30)).isoformat()
    with connect(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO profiles VALUES(?,?,0,'','','',0)", (tenant, user_id))
        changed = conn.execute("""UPDATE profiles SET version=version+1, value=?, source=?, expires_at=?, active=1
            WHERE tenant=? AND user_id=? AND version=?""",
            (value, "confirmação explícita no controle de preferência", expires, tenant, user_id, expected_version))
        if changed.rowcount != 1:
            raise ValueError("profile_conflict")
    return read_profile(tenant, user_id, db_path, now)


def revoke_profile(expected_version, tenant="loja_demo", user_id="U100", db_path=None):
    """Limpa o valor ativo; mantém versão. Não promete apagar backups ou traces antigos."""
    with connect(db_path) as conn:
        changed = conn.execute("""UPDATE profiles SET active=0, value='', source='', version=version+1
            WHERE tenant=? AND user_id=? AND version=?""", (tenant, user_id, expected_version))
        if changed.rowcount != 1:
            raise ValueError("profile_conflict")
    return read_profile(tenant, user_id, db_path)


def project_for_role(role, order, request, memory_context):
    """Exercício 3.1: allowlist. A logística não precisa de perfil ou conversa bruta."""
    if role == "logistics":
        return {"order": {k: order[k] for k in ("order_id", "shipment_id")},
                "request": "Consulte a situação atual da remessa verificada."}
    if role == "resolution":
        return {"order": {k: order[k] for k in ("order_id", "modality") if k in order},
                "request": "Consulte as opções condicionais do pedido; não execute ações.",
                "constraints": memory_context.get("constraints", [])}
    raise ValueError("unknown_role")


def merge_shared(board, role, proposal, expected_version):
    """Exercício 3.2: proposta em campo próprio; merge feito pelo coordenador."""
    if role not in ("logistics", "resolution") or set(proposal) != {role}:
        raise ValueError("field_not_owned")
    if expected_version != board["version"]:
        raise ValueError("board_conflict")
    return {**board, **proposal, "version": board["version"] + 1}
