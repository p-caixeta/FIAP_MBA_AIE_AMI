"""Cliente MCP 2.2: transporte real, escopo por operação e fechamento pelo SDK."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from mcp import Client, StdioServerParameters
from jsonschema import Draft202012Validator, ValidationError
from contracts import validate_result

ROOT = Path(__file__).resolve().parent


def connect_mcp(transport="stdio", alias="main", url=None, delay_s=0):
    """Somente servidores locais da aula. Nunca recebe shell/comando do modelo."""
    if alias not in ("main", "demo_a", "demo_b"):
        raise ValueError("invalid_server_alias")
    if transport == "http":
        if alias != "main":
            raise ValueError("demo_requires_stdio")
        target = url or os.getenv("MCP_HTTP_URL", "http://127.0.0.1:8005/mcp")
        parsed = urlparse(target)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password:
            raise ValueError("local_http_only")
        return Client(target, cache=None), target
    if transport != "stdio":
        raise ValueError("invalid_transport")
    script = ROOT / ("mcp_server.py" if alias == "main" else f"demos/{alias}.py")
    args = [str(script)] + (["--delay", str(delay_s)] if alias == "main" else [])
    # SDK usa allowlist do ambiente. Não passar os.environ, .env ou chave do host.
    params = StdioServerParameters(command=sys.executable, args=args, cwd=ROOT,
                                   env={"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"})
    return Client(params, cache=None), {"command": sys.executable, "args": args}


def normalize_tool_result(name, raw):
    data = raw.structured_content
    if raw.is_error:
        if isinstance(data, dict) and isinstance(data.get("error"), str):
            return {**data, "error_origin": "tool"}
        return {"error": "tool_execution_error", "error_origin": "tool",
                "detail": [block.text for block in raw.content if getattr(block, "type", None) == "text"]}
    if not isinstance(data, dict):
        return {"error": "invalid_tool_output", "error_origin": "contract"}
    try:
        validate_result(name, data)
    except (ValidationError, KeyError):
        return {"error": "invalid_tool_output", "error_origin": "contract"}
    return data


def classify_failure(error):
    if isinstance(error, BaseExceptionGroup):
        codes = [classify_failure(child) for child in error.exceptions]
        return "timeout" if "timeout" in codes else codes[0]
    if isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower():
        return "timeout"
    if isinstance(error, (ValueError, ValidationError)):
        return "invalid_arguments"
    if "MCP" in type(error).__name__ or "Mcp" in type(error).__name__:
        return "protocol_error"
    return "transport_unavailable"


async def request_mcp(action="discover", name=None, arguments=None, *, transport="stdio", alias="main",
                      url=None, timeout_s=None, delay_s=0, emit=None, call_id=None):
    """Timeout de startup separado do timeout da operação; ambos finitos."""
    emit = emit or (lambda *_a, **_k: None)
    call_id = call_id or str(uuid.uuid4())
    timeout_s = float(timeout_s if timeout_s is not None else os.getenv("MCP_TIMEOUT_S", "30"))
    started = time.perf_counter()
    client, target = connect_mcp(transport, alias, url, delay_s)
    scope = {"call_id": call_id, "alias": alias, "transport": transport}
    emit("mcp_connect", **scope, target=target)
    try:
        # fail_after/asyncio timeout ficam fora do context manager, para respeitar
        # o escopo de cancelamento dos task groups usados pelo SDK.
        async with asyncio.timeout(30 + timeout_s):
            async with client:
                emit("mcp_identity", **scope, server=client.server_info.model_dump(mode="json", by_alias=True) if client.server_info else None,
                     protocol=client.protocol_version)
                async with asyncio.timeout(timeout_s):
                    catalog = []
                    cursor = None
                    for _ in range(20):
                        page = await client.list_tools(cursor=cursor)
                        catalog.extend(t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in page.tools)
                        cursor = page.next_cursor
                        if not cursor:
                            break
                    else:
                        raise ValueError("catalog_page_limit")
                    emit("mcp_discovery", **scope, tools=catalog)
                    if action == "discover":
                        return {"tools": catalog, "protocol": client.protocol_version,
                                "server": client.server_info.model_dump(mode="json", by_alias=True) if client.server_info else None}
                    if action == "resource":
                        result = await client.read_resource("lab://corpus/manifest")
                        return {"contents": [part.model_dump(mode="json", by_alias=True) for part in result.contents]}
                    if action != "call":
                        raise ValueError("invalid_action")
                    selected = next((item for item in catalog if item["name"] == name), None)
                    if selected is None:
                        return {"error": "unknown_tool", "error_origin": "catalog"}
                    Draft202012Validator(selected["inputSchema"]).validate(arguments or {})
                    emit("mcp_call_start", **scope, name=name, arguments=arguments or {})
                    raw = await client.call_tool(name, arguments or {})
                    result = normalize_tool_result(name, raw)
                    emit("mcp_call_end", **scope, name=name, result=result,
                         envelope=raw.model_dump(mode="json", by_alias=True, exclude_none=True))
                    return result
    except Exception as error:
        code = classify_failure(error)
        emit("mcp_error", **scope, code=code, exception_type=type(error).__name__)
        return {"error": code, "error_origin": "contract" if code == "invalid_arguments" else "transport"}
    finally:
        emit("mcp_close", **scope, elapsed_ms=round(1000 * (time.perf_counter() - started)))


def discover_tools(**options):
    return asyncio.run(request_mcp("discover", **options))
