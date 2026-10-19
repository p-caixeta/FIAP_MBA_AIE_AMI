"""Regras pequenas, puras e independentes do provedor de LMM."""
from copy import deepcopy


def route_proposal(case: dict, analysis: dict, action: dict, evidence: list[dict]) -> str:
    """Ex. 2.2: toda escrita passa por revisão, mesmo com alta confiança."""
    if case.get("order_id") != "P600" or case.get("status") != "delivered":
        return "blocked"
    if analysis["conflicts"] or not analysis["observations"] or not evidence:
        return "request_evidence"
    if action["action"] == "answer":
        return "answer"
    if action["action"] == "request_evidence":
        return "request_evidence"
    if action["action"] == "create_damage_ticket":
        return "review"
    return "blocked"


def review_payload(proposal: dict) -> dict:
    """Ex. 2.3: mostre efeito, versão, lacunas e evidências antes da decisão."""
    fields = ("proposal_id", "version", "tool", "arguments", "rationale",
              "unknowns", "evidence_ids", "policy_version", "status")
    return {key: deepcopy(proposal[key]) for key in fields}


def validate_decision(proposal: dict, decision: dict) -> dict:
    """Ex. 3.1: aceite somente uma decisão explícita sobre a versão visível."""
    if not isinstance(decision, dict):
        raise ValueError("Decisão deve ser um objeto.")
    if set(decision) - {"proposal_id", "version", "action", "summary"}:
        raise ValueError("A decisão contém campos não permitidos.")
    if decision.get("proposal_id") != proposal["proposal_id"]:
        raise ValueError("Proposta diferente da revisão atual.")
    if type(decision.get("version")) is not int or decision["version"] != proposal["version"]:
        raise ValueError("Versão obsoleta: carregue a proposta atual.")
    if decision.get("action") not in {"approve", "reject", "revise", "request_evidence"}:
        raise ValueError("Escolha aprovar, rejeitar, revisar ou pedir evidência.")
    if decision["action"] == "revise":
        summary = decision.get("summary", "")
        if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 1000:
            raise ValueError("A revisão precisa de resumo de até 1.000 caracteres.")
        decision = {**decision, "summary": summary.strip()}
    elif "summary" in decision:
        raise ValueError("Use Revisar para alterar o resumo antes de aprovar.")
    return deepcopy(decision)
