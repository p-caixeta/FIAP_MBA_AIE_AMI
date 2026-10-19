"""SQLite local: proposta, decisão e efeito auditável, sem serviço externo."""
import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from config import DATA
from media import digest
from review import validate_decision


def load_data(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Store:
    """Conexões curtas; transações de escrita serializam as decisões no banco."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT, version INTEGER, cycle TEXT UNIQUE, body TEXT NOT NULL,
                    PRIMARY KEY(id, version));
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT, version INTEGER, body TEXT NOT NULL, result_version INTEGER,
                    PRIMARY KEY(id, version));
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY, proposal_id TEXT, version INTEGER, body TEXT NOT NULL,
                    UNIQUE(proposal_id, version));
            """)

    def connect(self):
        # Cada context manager abaixo fecha a conexão, além de commit/rollback.
        from contextlib import contextmanager

        @contextmanager
        def connection():
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                with db:
                    yield db
            finally:
                db.close()
        return connection()

    def _get(self, db, proposal_id: str, version: int | None = None) -> dict:
        query = "SELECT body FROM proposals WHERE id=?"
        args = [proposal_id]
        if version is not None:
            query += " AND version=?"
            args.append(version)
        row = db.execute(query + " ORDER BY version DESC LIMIT 1", args).fetchone()
        if row is None:
            raise ValueError("Proposta não encontrada.")
        return json.loads(row["body"])

    def get(self, proposal_id: str, version: int | None = None) -> dict:
        with self.connect() as db:
            return self._get(db, proposal_id, version)

    def list_proposals(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""SELECT body FROM proposals p WHERE version =
                (SELECT MAX(version) FROM proposals WHERE id=p.id) ORDER BY rowid DESC""")
            return [json.loads(row["body"]) for row in rows]

    def _put(self, db, proposal: dict, cycle: str):
        db.execute("INSERT OR REPLACE INTO proposals VALUES (?,?,?,?)",
                   (proposal["proposal_id"], proposal["version"], cycle, json.dumps(proposal)))

    def _update(self, db, proposal: dict):
        db.execute("UPDATE proposals SET body=? WHERE id=? AND version=?",
                   (json.dumps(proposal), proposal["proposal_id"], proposal["version"]))

    def save_proposal(self, thread: str, cycle: str, action: dict, analysis: dict,
                      evidence: list[dict], route: str, policy: dict) -> dict:
        """Salva a proposta uma vez, mesmo se o nó reiniciar antes do checkpoint."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT body FROM proposals WHERE cycle=?", (cycle,)).fetchone()
            if existing:
                return json.loads(existing["body"])
            row = db.execute("SELECT MAX(version) AS version FROM proposals WHERE id=?", (thread,)).fetchone()
            version = (row["version"] or 0) + 1
            if version > 1:
                previous = self._get(db, thread)
                if previous["status"] not in {"needs_evidence", "pending", "superseded"}:
                    raise ValueError("Caso encerrado: crie outro caso para nova demonstração.")
                previous["status"] = "superseded"
                self._update(db, previous)
            proposal = {
                "proposal_id": thread, "version": version, "case_id": "P600",
                "tool": action["action"], "arguments": {"order_id": "P600", "summary": action["summary"]},
                "rationale": action["rationale"], "unknowns": analysis["unknowns"],
                "evidence_ids": [e["id"] for e in evidence], "evidence": evidence,
                "evidence_hash": fingerprint(evidence), "policy_version": policy["version"],
                "policy_hash": fingerprint(policy), "route": route,
                "status": {"review": "pending", "answer": "answered",
                           "request_evidence": "needs_evidence", "blocked": "blocked"}[route],
            }
            self._put(db, proposal, cycle)
            return proposal

    def record_decision(self, proposal: dict, decision: dict) -> dict:
        """Persiste a revisão; repetir a mesma decisão devolve o resultado existente."""
        decision = validate_decision(proposal, decision)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM decisions WHERE id=? AND version=?",
                             (proposal["proposal_id"], proposal["version"])).fetchone()
            if old:
                if json.loads(old["body"]) != decision:
                    raise ValueError("Esta versão já recebeu outra decisão.")
                return self._get(db, proposal["proposal_id"], old["result_version"])
            current = self._get(db, proposal["proposal_id"])
            if current["version"] != proposal["version"] or current["status"] != "pending":
                raise ValueError("A proposta não está mais pendente nesta versão.")
            action = decision["action"]
            if action == "approve":
                self.check_evidence(current)
            current["status"] = {"approve": "approved", "reject": "rejected",
                                 "request_evidence": "needs_evidence", "revise": "superseded"}[action]
            current["reviewer"] = "professor-local"
            self._update(db, current)
            result = current
            if action == "revise":
                result = deepcopy(current)
                result.update(version=current["version"] + 1, status="pending")
                result["arguments"]["summary"] = decision["summary"]
                self._put(db, result, f"revision:{current['proposal_id']}:{current['version']}")
            db.execute("INSERT INTO decisions VALUES (?,?,?,?)",
                       (current["proposal_id"], current["version"], json.dumps(decision), result["version"]))
            return result

    def check_evidence(self, proposal: dict):
        if fingerprint(load_data("policy.json")) != proposal["policy_hash"]:
            raise ValueError("A política mudou: é necessária uma nova análise e aprovação.")
        if fingerprint(proposal["evidence"]) != proposal["evidence_hash"]:
            raise ValueError("Referências de evidência alteradas.")
        for item in proposal["evidence"]:
            if not Path(item["path"]).is_file() or digest(Path(item["path"])) != item["sha256"]:
                raise ValueError("A mídia mudou: é necessária uma nova análise e aprovação.")

    def execute_approved(self, proposal: dict) -> dict:
        """Ex. 3.2: autorizar e gravar na mesma transação evita tickets duplicados."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._get(db, proposal["proposal_id"])
            if current["version"] != proposal["version"]:
                raise ValueError("A aprovação pertence a uma versão obsoleta.")
            receipt = db.execute("SELECT body FROM tickets WHERE proposal_id=? AND version=?",
                                 (current["proposal_id"], current["version"])).fetchone()
            if receipt:
                return json.loads(receipt["body"])
            if current["status"] != "approved" or current["tool"] != "create_damage_ticket":
                raise ValueError("Execução bloqueada: falta aprovação da ferramenta permitida.")
            decision = db.execute("SELECT body FROM decisions WHERE id=? AND version=?",
                                  (current["proposal_id"], current["version"])).fetchone()
            if not decision or json.loads(decision["body"])["action"] != "approve":
                raise ValueError("Registro de aprovação ausente.")
            if current["arguments"]["order_id"] != "P600" or current["route"] != "review":
                raise ValueError("Caso ou rota não permitido.")
            self.check_evidence(current)
            ticket = {"ticket_id": "AV-" + uuid4().hex[:10], "proposal_id": current["proposal_id"],
                      "version": current["version"], **current["arguments"]}
            db.execute("INSERT INTO tickets VALUES (?,?,?,?)",
                       (ticket["ticket_id"], current["proposal_id"], current["version"], json.dumps(ticket)))
            current["status"] = "executed"
            self._update(db, current)
            return ticket

    def ticket_count(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
