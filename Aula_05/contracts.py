"""Contratos do laboratório, compartilhados por servidor, host e testes."""
from copy import deepcopy
from jsonschema import Draft202012Validator


def object_schema(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


TEXT = {"type": "string"}
ERROR = {"type": "object", "properties": {"error": TEXT}, "required": ["error"]}
INPUTS = {
    "get_order": object_schema({"order_id": {"type": "string", "pattern": "^P[0-9]+$"}}),
    "get_delivery_status": object_schema({"shipment_id": {"type": "string", "pattern": "^E[0-9]+$"}}),
    "get_resolution_options": object_schema({"order_id": {"type": "string", "pattern": "^P[0-9]+$"}}),
    "search_policies": object_schema({"query": {"type": "string", "minLength": 1, "maxLength": 4000},
                                      "top_k": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3}}, ["query"]),
}
OUTPUTS = {
    "get_order": object_schema({"order_id": TEXT, "shipment_id": TEXT, "status": TEXT,
                                "modality": TEXT, "items": {"type": "array", "items": TEXT}}),
    "get_delivery_status": object_schema({"shipment_id": TEXT, "status": TEXT,
                                          "last_event": TEXT, "eta": {"type": ["string", "null"]}}),
    "get_resolution_options": object_schema({"rule_id": TEXT, "rule_version": TEXT,
        "options": {"type": "array", "items": object_schema({"action": TEXT, "available": {"type": "boolean"}, "requires": TEXT})},
        "refund_available": {"type": "boolean"}}),
    "search_policies": object_schema({"query": TEXT, "status": TEXT, "top_k": {"type": "integer"},
        "hits": {"type": "array", "items": {"type": "object", "required": ["chunk_id", "doc_id", "text", "version", "source_path", "tenant_id"],
        "properties": {key: TEXT for key in ("chunk_id", "doc_id", "text", "version", "source_path", "tenant_id")}}}}),
}
DESCRIPTIONS = {
    "get_order": "Consulta um pedido Pxxx e sua remessa; não executa ações.",
    "get_delivery_status": "Consulta o status de uma remessa.",
    "get_resolution_options": "Consulta opções condicionais para um pedido; não abre chamado nem reembolsa.",
    "search_policies": "Busca políticas vigentes no corpus sintético, com texto e proveniência.",
}


def validate_arguments(name, arguments):
    if name not in INPUTS:
        raise ValueError("unknown_tool")
    Draft202012Validator(INPUTS[name]).validate(arguments)
    if name == "search_policies" and not arguments["query"].strip():
        raise ValueError("empty_query")


def validate_result(name, result):
    Draft202012Validator({"anyOf": [OUTPUTS[name], ERROR]}).validate(result)
    return result


def local_catalog():
    """Baseline local somente; em MCP o catálogo vem de tools/list."""
    return [{"name": name, "description": DESCRIPTIONS[name],
             "inputSchema": deepcopy(schema), "outputSchema": deepcopy(OUTPUTS[name])}
            for name, schema in INPUTS.items()]
