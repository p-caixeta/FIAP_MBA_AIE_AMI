"""Grafo linear com uma pausa real e duas ramificações de revisão."""
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from media import build_multimodal_input, input_summary
from reasoning import analyze_evidence, propose_action, provided_analysis
from review import review_payload, route_proposal, validate_decision
from store import Store, load_data


class State(TypedDict, total=False):
    thread: str
    cycle: str
    message: str
    evidence: list[dict]
    mode: str
    fixture: str
    analysis: dict
    action: dict
    proposal: dict
    decision: dict
    receipt: dict
    metrics: dict
    events: list[dict]


def event(state: State, name: str, detail: dict) -> list[dict]:
    return state.get("events", []) + [{"step": name, "detail": detail}]


def human_review(state: State) -> dict:
    """Ex. 3.1: pause sem escrita; este nó reinicia quando chega a decisão."""
    decision = interrupt(review_payload(state["proposal"]))
    return {"decision": validate_decision(state["proposal"], decision)}


def build_graph(store: Store, checkpointer):
    """Poucos nós; regras e persistência ficam em funções que podem ser testadas."""
    def analyze(state):
        if state["mode"] == "live":
            analysis, metrics = analyze_evidence(state["message"], state["evidence"])
        else:
            analysis = provided_analysis(state["fixture"], state["evidence"])
            metrics = {"mode": "provided", "model": None, "usage": None,
                       "input": input_summary(build_multimodal_input(state["message"], state["evidence"]))}
        return {"analysis": analysis, "metrics": {"analysis": metrics},
                "events": event(state, "analysis_completed", {"analysis": analysis, "metrics": metrics})}

    def propose(state):
        policy = load_data("policy.json")
        if state["mode"] == "live":
            action, metrics = propose_action(load_data("case.json"), policy, state["analysis"], state["message"])
        else:
            action = {"action": "create_damage_ticket", "summary": state["analysis"]["summary"],
                      "rationale": "Proposta fornecida para exercitar revisão humana."}
            metrics = {"mode": "provided", "model": None, "usage": None}
        route = route_proposal(load_data("case.json"), state["analysis"], action, state["evidence"])
        proposal = store.save_proposal(state["thread"], state["cycle"], action,
                                       state["analysis"], state["evidence"], route, policy)
        return {"proposal": proposal, "metrics": {**state["metrics"], "proposal": metrics},
                "events": event(state, "proposal_created", {"route": route, **review_payload(proposal)})}

    def decide(state):
        proposal = store.record_decision(state["proposal"], state["decision"])
        return {"proposal": proposal, "events": event(state, "review_recorded",
                {"decision": state["decision"], "status": proposal["status"], "version": proposal["version"]})}

    def execute(state):
        # O banco torna este efeito idempotente, inclusive após queda antes do checkpoint.
        receipt = store.execute_approved(state["proposal"])
        return {"receipt": receipt, "events": event(state, "action_executed", receipt)}

    graph = StateGraph(State)
    for name, function in [("analyze", analyze), ("propose", propose), ("review", human_review),
                           ("decide", decide), ("execute", execute)]:
        graph.add_node(name, function)
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "propose")
    graph.add_conditional_edges("propose", lambda s: "review" if s["proposal"]["route"] == "review" else END)
    graph.add_edge("review", "decide")
    graph.add_conditional_edges("decide", lambda s: {"approved": "execute", "pending": "review"}
                                .get(s["proposal"]["status"], END))
    graph.add_edge("execute", END)
    return graph.compile(checkpointer=checkpointer)


def resume_case(graph, store: Store, thread: str, decision: dict) -> dict:
    """Ex. 3.2: confira a versão e retome a mesma execução persistida."""
    config = {"configurable": {"thread_id": thread}}
    snapshot = graph.get_state(config)
    if not snapshot.values:
        raise ValueError("Execução não encontrada.")
    proposal = snapshot.values["proposal"]
    decision = validate_decision(proposal, decision)
    if snapshot.next == ("review",):
        if store.get(thread)["status"] != "pending":
            raise ValueError("A revisão não está pendente.")
        return graph.invoke(Command(resume=decision), config)
    # Uma falha após registrar a decisão pode deixar decide/execute pendente.
    store.record_decision(proposal, decision)
    if snapshot.next:
        return graph.invoke(None, config)
    return dict(snapshot.values)


@contextmanager
def open_workflow(directory: Path):
    """Fechar/reabrir este contexto preserva o thread no SQLite."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    store = Store(directory / "actions.sqlite3")
    with SqliteSaver.from_conn_string(str(directory / "checkpoints.sqlite3")) as checkpointer:
        yield Runtime(store, build_graph(store, checkpointer))


class Runtime:
    """Uma trava por processo simplifica a demonstração Flask local."""

    def __init__(self, store, graph):
        self.store, self.graph, self.lock = store, graph, RLock()

    def start(self, message: str, evidence: list[dict], mode="provided",
              fixture="clear", thread: str | None = None) -> dict:
        if mode not in {"provided", "live"}:
            raise ValueError("Modo inválido.")
        # Validação ocorre inclusive no modo fornecido; antes de qualquer nó/API.
        build_multimodal_input(message, evidence)
        with self.lock:
            if thread:
                if self.store.get(thread)["status"] not in {"pending", "needs_evidence"}:
                    raise ValueError("Caso encerrado: abra uma nova demonstração.")
            thread = thread or uuid4().hex
            state = {"thread": thread, "cycle": uuid4().hex, "message": message,
                     "evidence": evidence, "mode": mode, "fixture": fixture,
                     "events": [], "receipt": {}, "decision": {}}
            self.graph.invoke(state, {"configurable": {"thread_id": thread}})
            return self.snapshot(thread)

    def resume(self, thread: str, decision: dict) -> dict:
        with self.lock:
            resume_case(self.graph, self.store, thread, decision)
            return self.snapshot(thread)

    def snapshot(self, thread: str) -> dict:
        with self.lock:
            snapshot = self.graph.get_state({"configurable": {"thread_id": thread}})
            if not snapshot.values:
                raise ValueError("Execução não encontrada.")
            result = dict(snapshot.values)
            result["proposal"] = self.store.get(thread)
            result["pending"] = bool(snapshot.next)
            return result
