"""Os três grafos de aula, com o fan-out e a junção da Aula 02 preservados."""

from __future__ import annotations

import re
import threading
import time
from copy import deepcopy
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agents import _increment, resolve_citations, run_specialist, synthesize_agentic, synthesize_baseline, synthesize_fixed
from config import MAX_EVIDENCE_CHUNKS, RUN_DEADLINE_S, TOP_K, build_id, configured_model
from retrieval import build_query, search_policies
from tools import get_order
from tool_gateway import call_operation, INTEGRATIONS, TRANSPORTS
from memory import load_thread, new_thread, save_turn, read_profile, project_for_role, merge_shared
from context import select_context, update_case_state


STAGES = {"baseline", "fixed_rag", "agentic_rag"}
ORDER_ID_RE = re.compile(r"\bP\d+\b", re.IGNORECASE)


class TeamState(TypedDict, total=False):
    request: str
    history: list[dict]
    order_id: str
    order: dict
    route: str
    logistics: dict
    resolution: dict
    evidence: list[dict]
    output: dict


def _runtime() -> dict:
    return {
        "started_at": time.perf_counter(),
        "deadline": time.monotonic() + RUN_DEADLINE_S,
        "lock": threading.Lock(),
        "registry": {},
        "metrics": {"model_calls": 0, "tool_calls": 0, "searches": 0, "input_tokens": 0, "output_tokens": 0},
        "usage_seen": False,
    }


def _extract_order_id(message: str, history: list[dict]) -> tuple[str | None, str | None]:
    current = sorted(set(match.upper() for match in ORDER_ID_RE.findall(message)))
    if len(current) > 1:
        return None, "Encontrei mais de um pedido. Informe apenas um identificador Pxxx."
    if current:
        return current[0], None
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        candidates = sorted(set(match.upper() for match in ORDER_ID_RE.findall(item.get("content", ""))))
        if len(candidates) == 1:
            return candidates[0], None
    return None, "Informe o identificador do pedido no formato Pxxx para continuar."


def _tool_call(emit, runtime: dict, name: str, arguments: dict, callback, call_id: str) -> dict:
    if time.monotonic() >= runtime["deadline"]:
        raise TimeoutError("Prazo lógico da execução esgotado antes da próxima ferramenta.")
    _increment(runtime, "tool_calls")
    emit("tool_start", name=name, arguments=arguments, call_id=call_id)
    result = callback(**arguments)
    emit("tool_end", name=name, result=result, status="error" if result.get("error") else "ok", call_id=call_id)
    return result


def _deliver_hits(runtime: dict, result: dict) -> dict:
    """Limita contexto acumulado sem ocultar quais hits chegaram ao modelo."""
    delivered, omitted = [], 0
    with runtime["lock"]:
        registry = runtime["registry"]
        for hit in result["hits"]:
            if hit["chunk_id"] in registry or len(registry) < MAX_EVIDENCE_CHUNKS:
                registry.setdefault(hit["chunk_id"], deepcopy(hit))
                delivered.append(deepcopy(hit))
            else:
                omitted += 1
    return {**result, "hits": delivered, "omitted_count": omitted}


def _search_with_events(query: str, runtime: dict, emit, call_id: str) -> dict:
    if time.monotonic() >= runtime["deadline"]:
        raise TimeoutError("Prazo lógico da execução esgotado antes da busca.")
    _increment(runtime, "tool_calls")
    emit("tool_start", name="search_policies", arguments={"query": query, "top_k": TOP_K}, call_id=call_id)
    raw = call_operation("retrieval", "search_policies", {"query": query, "top_k": TOP_K}, runtime, emit, call_id=call_id)
    if raw.get("error"):
        raw = {**raw, "query": query, "top_k": TOP_K, "status": "error", "hits": []}
    result = _deliver_hits(runtime, raw)
    _increment(runtime, "searches")
    emit(
        "retrieval_result",
        query=result["query"],
        hits=result["hits"],
        status=result["status"],
        search_index=runtime["metrics"]["searches"],
        top_k=result["top_k"],
        omitted_count=result["omitted_count"],
        call_id=call_id,
    )
    emit("tool_end", name="search_policies", result=result, status=result["status"], call_id=call_id)
    return result


def build_graph(stage: str, emit, runtime: dict | None = None):
    """Compila a topologia real da etapa, incluindo a junção por lista de origem."""
    if stage not in STAGES:
        raise ValueError("Etapa inválida")
    runtime = runtime or _runtime()
    workflow = StateGraph(TeamState)

    def node(node_id: str, label: str, body):
        def wrapped(state: TeamState):
            emit("node_start", node_id=node_id, label=label)
            status = "completed"
            try:
                update = body(state)
                if update.get(node_id, {}).get("error"):
                    status = "partial"
                if update.get("output", {}).get("status") in {"partial", "failed"}:
                    status = update["output"]["status"]
                return update
            except Exception as error:
                status = "failed"
                raise error
            finally:
                emit("node_end", node_id=node_id, label=label, status=status)
        return wrapped

    def prepare(state: TeamState):
        order_id, message = _extract_order_id(state["request"], state.get("history", []))
        if not order_id:
            return {"route": "end", "output": _base_output("needs_input", message)}
        order = _tool_call(emit, runtime, "get_order", {"order_id": order_id},
                           lambda **args: call_operation("prepare", "get_order", args, runtime, emit, call_id="prepare-order"), "prepare-order")
        if order.get("error"):
            missing = order["error"] == "order_not_found"
            output = _base_output("not_found" if missing else "failed",
                                  "Não encontrei esse pedido." if missing else "Não foi possível consultar o pedido; existência não confirmada.")
            output["facts"] = [order]
            return {"route": "end", "output": output}
        return {"route": "fan_out", "order_id": order_id, "order": order}

    def logistics(state: TeamState):
        order, request = specialist_input("logistics", state)
        result = run_specialist("logistics", order, request, runtime, emit)
        return {"logistics": result}

    def resolution(state: TeamState):
        order, request = specialist_input("resolution", state)
        result = run_specialist("resolution", order, request, runtime, emit)
        return {"resolution": result}

    def specialist_input(role, state):
        if runtime.get("memory_mode") == "shared":
            projected = project_for_role(role, state["order"], state["request"], runtime["memory_context"])
            emit("memory_projection", role=role, payload=projected)
            request = projected["request"]
            if projected.get("constraints"):
                request += " Restrições declaradas: " + str(projected["constraints"])
            return projected["order"], request
        return state["order"], state["request"]

    def retrieve(state: TeamState):
        query = build_query(state["request"], state["order"], state["logistics"], state["resolution"])
        result = _search_with_events(query, runtime, emit, "fixed-retrieval")
        return {"evidence": result["hits"]}

    def synthesize(state: TeamState):
        if runtime.get("memory_mode") == "shared":
            board = {"version": 0}
            for role in ("logistics", "resolution"):
                board = merge_shared(board, role, {role: state[role]}, board["version"])
            emit("memory_merge", board=board, note="Junção aguarda ambos; campos separados, merge sequencial.")
        if stage == "baseline":
            output = synthesize_baseline(state["order"], state["logistics"], state["resolution"])
        elif stage == "fixed_rag":
            output = synthesize_fixed(state["request"], state["order"], state["logistics"], state["resolution"], state.get("evidence", []), runtime, emit)
        else:
            output = synthesize_agentic(
                state["request"],
                state["order"],
                state["logistics"],
                state["resolution"],
                lambda query, call_id: _search_with_events(query, runtime, emit, call_id),
                runtime,
                emit,
            )
        citations, warnings = resolve_citations(output["answer"], runtime["registry"])
        output["citations"] = citations
        output["warnings"] = output.get("warnings", []) + warnings
        return {"output": output}

    workflow.add_node("prepare", node("prepare", "Preparar", prepare))
    workflow.add_node("logistics", node("logistics", "Logística", logistics))
    workflow.add_node("resolution", node("resolution", "Resolução", resolution))
    if stage == "fixed_rag":
        workflow.add_node("retrieve_policies", node("retrieve_policies", "Buscar políticas", retrieve))
    synthesis_label = {"baseline": "Síntese — Python", "fixed_rag": "Síntese — LLM + evidências", "agentic_rag": "Síntese — agente com busca"}[stage]
    workflow.add_node("synthesize", node("synthesize", synthesis_label, synthesize))
    workflow.add_edge(START, "prepare")
    workflow.add_conditional_edges(
        "prepare", lambda state: ["logistics", "resolution"] if state["route"] == "fan_out" else END,
        {"logistics": "logistics", "resolution": "resolution", END: END},
    )
    if stage == "fixed_rag":
        workflow.add_edge(["logistics", "resolution"], "retrieve_policies")
        workflow.add_edge("retrieve_policies", "synthesize")
    else:
        workflow.add_edge(["logistics", "resolution"], "synthesize")
    workflow.add_edge("synthesize", END)
    return workflow.compile()


def _base_output(status: str, answer: str) -> dict:
    return {
        "status": status,
        "answer": answer,
        "citations": [],
        "warnings": [],
        "facts": [],
        "missing_information": [],
    }


def _static_graph(stage: str) -> dict:
    labels = {
        "prepare": "Preparar", "logistics": "Logística", "resolution": "Resolução",
        "retrieve_policies": "Buscar políticas", "synthesize": "Síntese",
    }
    nodes = ["__start__", "prepare", "logistics", "resolution"]
    edges = [["__start__", "prepare"], ["prepare", "logistics"], ["prepare", "resolution"], ["prepare", "__end__"]]
    if stage == "fixed_rag":
        nodes.append("retrieve_policies")
        edges += [["logistics", "retrieve_policies"], ["resolution", "retrieve_policies"], ["retrieve_policies", "synthesize"]]
    else:
        edges += [["logistics", "synthesize"], ["resolution", "synthesize"]]
    nodes += ["synthesize", "__end__"]
    return {
        "stage": stage,
        "nodes": [{"id": item, "label": labels.get(item, item)} for item in nodes],
        "edges": [{"from": source, "to": target} for source, target in edges],
        "synthesis": {"baseline": "Python", "fixed_rag": "LLM + evidências", "agentic_rag": "agente com busca"}[stage],
    }


def graph_description(stage: str) -> dict:
    """Obtém o grafo compilado antes de serializar a descrição usada pela interface."""
    compiled = build_graph(stage, lambda *_args, **_kwargs: None)
    compiled_graph = compiled.get_graph()
    description = _static_graph(stage)
    labels = {node["id"]: node["label"] for node in description["nodes"]}
    description["nodes"] = [{"id": node_id, "label": labels.get(node_id, node_id)} for node_id in compiled_graph.nodes]
    description["edges"] = [
        {"from": edge.source, "to": edge.target, "conditional": edge.conditional}
        for edge in compiled_graph.edges
    ]
    return description


def run_case(message: str, stage: str = "fixed_rag", history: list[dict] | None = None, emit=None,
             thread_id=None, memory_mode="shared", strategy="structured", db_path=None,
             tenant="loja_demo", user_id="U100", integration="mcp_tools_rag", transport="stdio") -> dict:
    """Entrada pública única de app e notebooks."""
    if stage not in STAGES:
        raise ValueError("Etapa inválida")
    if integration not in INTEGRATIONS or transport not in TRANSPORTS:
        raise ValueError("invalid_mcp_configuration")
    if memory_mode not in ("off", "short", "long", "shared"):
        raise ValueError("invalid_memory_mode")
    if tenant != "loja_demo":
        raise ValueError("operational_tenant_not_available")
    runtime = _runtime()
    runtime.update(integration=integration, transport=transport)
    emit = emit or (lambda *_args, **_kwargs: None)
    description = graph_description(stage)
    emit("run_start", stage=stage, build_id=build_id(), graph=description, model=configured_model(), request=message,
         integration=integration, transport=transport)
    snapshot = {"version": 0, "turns": [], "state": {}}
    profile = None
    if memory_mode != "off":
        thread_id = thread_id or new_thread(tenant, user_id, db_path)
        snapshot = load_thread(thread_id, tenant, user_id, db_path)
    if memory_mode in ("long", "shared"):
        profile = read_profile(tenant, user_id, db_path)
    selected = select_context(snapshot, strategy if memory_mode != "off" else "none", profile)
    # Uma restrição no turno atual vale imediatamente, antes de qualquer subagente.
    explicit_ids = sorted(set(ORDER_ID_RE.findall(message.upper())))
    if len(explicit_ids) == 1 and selected.get("order_id") != explicit_ids[0]:
        # Não transportar restrições específicas de outro pedido; perfil é independente.
        selected = {k: v for k, v in selected.items() if k in ("response_style", "profile_version")}
        selected["order_id"] = explicit_ids[0]
    selected = update_case_state(selected, message)
    runtime.update(memory_context=selected, memory_mode=memory_mode)
    emit("memory_read", thread_id=thread_id, mode=memory_mode, strategy=strategy,
         stored_turns=len(snapshot["turns"]), selected=selected, version=snapshot["version"])
    selected_history = []
    if selected.get("order_id"):
        selected_history.append({"role": "user", "content": selected["order_id"]})
    for turn in selected.get("recent_turns", []):
        selected_history.extend([{"role": "user", "content": turn["request"]}])
    compiled = build_graph(stage, emit, runtime)
    result = compiled.invoke({"request": message, "history": selected_history})
    output = result.get("output") or _base_output("failed", "A execução terminou sem resposta.")
    if memory_mode != "off":
        case_state = update_case_state(snapshot["state"], message, result.get("order_id"))
        version = save_turn(thread_id, snapshot["version"], case_state,
                            {"request": message, "status": output["status"]}, tenant, user_id, db_path)
        emit("memory_write", thread_id=thread_id, version=version, state=case_state)
    output["thread_id"] = thread_id
    output["memory_mode"] = memory_mode
    output["memory_strategy"] = strategy
    elapsed_ms = round((time.perf_counter() - runtime["started_at"]) * 1000)
    metrics = {**runtime["metrics"], "elapsed_ms": elapsed_ms}
    if not runtime["usage_seen"] or runtime.get("usage_missing"):
        metrics["input_tokens"] = None
        metrics["output_tokens"] = None
    output["metrics"] = metrics
    emit("run_end", output=output, metrics=metrics, build_id=build_id())
    return output
