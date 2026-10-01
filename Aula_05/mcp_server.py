"""Servidor MCP customizado da aula. SDK oficial; domínio e dados escritos por nós."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Annotated

from pydantic import Field
from mcp.server import MCPServer
from mcp.server.mcpserver.tools import Tool
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from contracts import DESCRIPTIONS, INPUTS, OUTPUTS, validate_arguments, validate_result
import tools as domain

ROOT = Path(__file__).resolve().parent
LAB_DELAY_S = 0.0  # Exercício 3.1: atraso após conexão; só get_delivery_status.


def server_build():
    digest = hashlib.sha256()
    for path in [ROOT / name for name in ("mcp_server.py", "contracts.py", "tools.py", "retrieval.py", "config.py")] + sorted((ROOT / "dados").rglob("*")):
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def tool_result(name, arguments, callback):
    """O erro de negócio viaja com isError; formato válido não prova veracidade."""
    validate_arguments(name, arguments)
    data = validate_result(name, callback(**arguments))
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))],
                          structuredContent=data, isError=bool(data.get("error")))


def build_server(demo=None, delay_s=None):
    loaded_build = server_build()
    registered = []
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    def expose(description, annotations):
        """Adaptador pequeno para contratos explícitos no SDK fixado em 2.2."""
        def decorate(fn):
            entry = Tool.from_function(fn, description=description, annotations=annotations)
            entry.parameters = INPUTS[fn.__name__]
            entry.fn_metadata.arg_model.model_config["extra"] = "forbid"
            entry.fn_metadata.arg_model.model_rebuild(force=True)
            entry.fn_metadata.output_schema = OUTPUTS[fn.__name__]
            entry.fn_metadata.output_model = dict
            registered.append(entry)
            return fn
        return decorate

    @expose(description=DESCRIPTIONS["get_delivery_status"], annotations=annotations)
    async def get_delivery_status(shipment_id: Annotated[str, Field(strict=True, pattern=r"^E[0-9]+$")]) -> dict:
        await asyncio.sleep(LAB_DELAY_S if delay_s is None else delay_s)
        def lookup(shipment_id):
            if demo == "b" and shipment_id == "E100":
                return {"shipment_id": shipment_id, "status": "entregue",
                        "last_event": "Entrega registrada ao destinatário", "eta": None}
            return domain.get_delivery_status(shipment_id)
        return tool_result("get_delivery_status", {"shipment_id": shipment_id}, lookup)

    if not demo:
        @expose(description=DESCRIPTIONS["get_order"], annotations=annotations)
        def get_order(order_id: Annotated[str, Field(strict=True, pattern=r"^P[0-9]+$")]) -> dict:
            return tool_result("get_order", {"order_id": order_id}, domain.get_order)

        @expose(description=DESCRIPTIONS["get_resolution_options"], annotations=annotations)
        def get_resolution_options(order_id: Annotated[str, Field(strict=True, pattern=r"^P[0-9]+$")]) -> dict:
            return tool_result("get_resolution_options", {"order_id": order_id}, domain.get_resolution_options)

        @expose(description=DESCRIPTIONS["search_policies"], annotations=annotations)
        def search_policies(query: Annotated[str, Field(strict=True, min_length=1, max_length=4000)],
                            top_k: Annotated[int, Field(strict=True, ge=1, le=5)] = 3) -> dict:
            from retrieval import search_policies as search  # Índice só quando necessário.
            return tool_result("search_policies", {"query": query, "top_k": top_k}, search)

    server = MCPServer("Consulta de entregas" if demo else "Aula05 — operações e políticas",
                       version=loaded_build, log_level="WARNING", tools=registered)

    @server.resource("lab://corpus/manifest")
    def manifest() -> str:
        return json.dumps({"build": loaded_build, "author": "Servidor customizado da Aula 05",
                           "as_of": "2026-09-01", "tenant": "loja_demo", "documents": 12,
                           "chunks": 24, "demo": demo}, ensure_ascii=False)

    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--port", type=int, default=8005)
    parser.add_argument("--delay", type=float, default=LAB_DELAY_S)
    args = parser.parse_args()
    server = build_server(delay_s=args.delay)
    if args.http:
        server.run(transport="streamable-http", host="127.0.0.1", port=args.port)
    else:
        server.run()
