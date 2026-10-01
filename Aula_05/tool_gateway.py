"""Fronteira do host: descoberta não concede permissão de execução."""
import asyncio
from copy import deepcopy
from jsonschema import ValidationError
from contracts import local_catalog, validate_arguments, validate_result
from mcp_client import discover_tools, request_mcp

INTEGRATIONS = {"local", "mcp_tools", "mcp_tools_rag"}
TRANSPORTS = {"stdio", "http"}
# Política do executor: independente do filtro didático oferecido ao modelo.
EXECUTION_POLICY = {"prepare": {"get_order"}, "logistics": {"get_delivery_status"},
                    "resolution": {"get_resolution_options"}, "retrieval": {"search_policies"}}


def select_tools_for_role(catalog, role):
    """Exercício 2.1: altere a oferta; a política de execução continua separada."""
    offered = {"logistics": {"get_delivery_status"}, "resolution": {"get_resolution_options"},
               "retrieval": {"search_policies"}, "prepare": {"get_order"}}
    return [deepcopy(item) for item in catalog if item["name"] in offered.get(role, set())]


def build_mcp_arguments(name, context):
    """Exercício 2.3: contexto do host não é payload automático do servidor."""
    fields = {"get_order": ("order_id",), "get_delivery_status": ("shipment_id",),
              "get_resolution_options": ("order_id",), "search_policies": ("query", "top_k")}
    return {key: context[key] for key in fields[name] if key in context}


def validate_tool_call(role, name, arguments, scope=None):
    if name not in EXECUTION_POLICY.get(role, set()):
        return {"error": "tool_not_allowed", "error_origin": "host"}
    try:
        validate_arguments(name, arguments)
    except (ValueError, ValidationError):
        return {"error": "invalid_arguments", "error_origin": "host"}
    scope = scope or {}
    required_scope = {"logistics": "shipment_id", "resolution": "order_id"}.get(role)
    if required_scope and required_scope not in scope:
        return {"error": "scope_unavailable", "error_origin": "host"}
    for field in ("order_id", "shipment_id"):
        if field in arguments and field in scope and arguments[field] != scope[field]:
            return {"error": field.replace("_id", "") + "_not_allowed", "error_origin": "host"}
    return None


def uses_mcp(name, runtime):
    mode = runtime.get("integration", "mcp_tools_rag")
    return mode != "local" and (name != "search_policies" or mode == "mcp_tools_rag")


def catalog_for_role(role, runtime, emit):
    expected = next(iter(EXECUTION_POLICY[role]))
    if uses_mcp(expected, runtime):
        result = discover_tools(transport=runtime.get("transport", "stdio"), emit=emit)
        if result.get("error"):
            return [], result
        catalog = result["tools"]
    else:
        catalog = local_catalog()
    selected = select_tools_for_role(catalog, role)
    emit("tools_selected", role=role, tools=selected)
    return selected, None


def call_operation(role, name, arguments, runtime, emit, scope=None, call_id=None):
    denied = validate_tool_call(role, name, arguments, scope)
    if denied:
        emit("tool_denied", role=role, name=name, arguments=arguments, result=denied)
        return denied
    payload = build_mcp_arguments(name, arguments)
    if uses_mcp(name, runtime):
        return asyncio.run(request_mcp("call", name, payload, transport=runtime.get("transport", "stdio"),
                                       emit=emit, call_id=call_id))
    if name == "search_policies":
        from retrieval import search_policies
        result = search_policies(**payload)
    else:
        import tools
        result = getattr(tools, name)(**payload)
    try:
        validate_result(name, result)
    except ValidationError:
        return {"error": "invalid_tool_output", "error_origin": "contract"}
    return {**result, "error_origin": "tool"} if result.get("error") else result
