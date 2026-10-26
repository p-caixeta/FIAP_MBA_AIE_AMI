"""Clientes pequenos. Nenhum servidor MCP ou A2A é criado ou modificado aqui."""
import asyncio
import json
from urllib.request import Request, urlopen
from uuid import uuid4

from langchain_core.tools import StructuredTool
from mcp import Client, StdioServerParameters


def mcp_client(spec):
    if "url" in spec:
        if not spec["url"]:
            raise ValueError("Configure AULA07_MCP_URL antes de conectar MathServer.")
        target = spec["url"]
    else:
        target = StdioServerParameters(command=spec["command"], args=spec.get("args", []))
    # Expansão: autenticação e pooling entram na criação deste cliente.
    return Client(target, cache=None, read_timeout_seconds=25)


async def _mcp(spec, name=None, arguments=None):
    async with mcp_client(spec) as client:
        if name is None:
            tools, cursor = [], None
            while True:
                page = await client.list_tools(cursor=cursor)
                tools.extend(t.model_dump(by_alias=True, exclude_none=True) for t in page.tools)
                cursor = page.next_cursor
                if not cursor:
                    return tools
        result = await client.call_tool(name, arguments)
        if result.is_error:
            raise ValueError(f"MCP {name}: " + str(result.content))
        return result.structured_content or "\n".join(
            p.text for p in result.content if getattr(p, "type", "") == "text")


def discover_mcp(servers):
    return {alias: asyncio.run(_mcp(spec)) for alias, spec in servers.items()}


def mcp_tools(servers, catalog):
    tools = []
    for alias, items in catalog.items():
        for item in items:
            def call(_spec=servers[alias], _name=item["name"], **arguments):
                return asyncio.run(_mcp(_spec, _name, arguments))
            tools.append(StructuredTool.from_function(
                func=call, name=f"{alias}__{item['name']}",
                description=item.get("description") or item["name"],
                args_schema=item["inputSchema"]))
    return tools


def request_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=45) as response:
        return json.load(response)


def discover_agents(agents):
    cards = {}
    for alias, spec in agents.items():
        if not spec.get("url"):
            raise ValueError("Configure AULA07_A2A_URL antes de conectar o redator.")
        if spec.get("card_url"):
            cards[alias] = {"source": "Agent Card remoto", "card": request_json(spec["card_url"])}
        else:
            # O notebook não publica um card: não fingir descoberta remota.
            cards[alias] = {"source": "Cadastro local · formato do notebook",
                            "card": {"name": alias, "url": spec["url"],
                                     "description": spec.get("description", "Redator externo")}}
    return cards


def ask_agent(spec, text, context_id):
    """Preserva exatamente o contrato do Servidor_A2A.ipynb fornecido."""
    result = request_json(spec["url"], {
        "jsonrpc": "2.0", "method": "message/send", "id": uuid4().int % 1_000_000,
        "params": {"contextId": context_id, "message": {"text": text, "type": "TEXT"}}})
    if "error" in result:
        raise ValueError(f"A2A: {result['error']}")
    return "\n\n".join(a["text"] for a in result["result"]["artifacts"] if "text" in a)
