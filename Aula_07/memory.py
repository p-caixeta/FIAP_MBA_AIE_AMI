"""Uma conversa recente e uma preferência; SQLite sobrevive ao reload local."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / "runtime"


@contextmanager
def connect():
    RUNTIME.mkdir(exist_ok=True)
    db = sqlite3.connect(RUNTIME / "memory.sqlite3")
    db.execute("CREATE TABLE IF NOT EXISTS turns (session TEXT, role TEXT, content TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY, preference TEXT)")
    try:
        with db:
            yield db
    finally:
        db.close()


def read(session):
    with connect() as db:
        rows = db.execute("SELECT role, content FROM turns WHERE session=? ORDER BY rowid DESC LIMIT 8",
                          (session,)).fetchall()
        preference = db.execute("SELECT preference FROM profile WHERE id=1").fetchone()
    return {"history": [{"role": r, "content": c} for r, c in reversed(rows)],
            "preference": preference[0] if preference else ""}


def remember(session, request, plan):
    with connect() as db:
        db.executemany("INSERT INTO turns VALUES (?, ?, ?)", [
            (session, "user", request),
            (session, "assistant", json.dumps(plan, ensure_ascii=False))])
    # Expansão: resumir ou recuperar episódios em vez desta janela de oito turnos.


def save_preference(value):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO profile VALUES (1, ?)", (value,))
    # Perfil único da demonstração local; em produção, associar ao usuário autenticado.
