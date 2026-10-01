"""Diagnóstico sem LLM: python Aula_05/diagnostics.py --compare."""
import argparse
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from mcp_client import request_mcp


async def compare_demo_servers(emit=None):
    """Mesmas entradas e schemas; B mente deliberadamente sobre a fixture E100."""
    records = {}
    for alias in ("demo_a", "demo_b"):
        catalog = await request_mcp("discover", alias=alias, emit=emit)
        result = await request_mcp("call", "get_delivery_status", {"shipment_id": "E100"}, alias=alias, emit=emit)
        records[alias] = {"catalog": catalog, "result": result,
                          "answer": "Consulta falhou." if result.get("error") else
                          f"A remessa consta como {result['status']}. Previsão: {result.get('eta') or 'não se aplica'}."}
    a, b = (records[key] for key in ("demo_a", "demo_b"))
    records["same_catalog"] = bool(a["catalog"].get("tools")) and a["catalog"].get("tools") == b["catalog"].get("tools")
    records["same_result"] = a["result"] == b["result"]
    records["reference"] = "dados/shipments.json: E100 está atrasado; B contém adulteração didática explícita."
    return records


@contextmanager
def local_http_server():
    """Processo próprio em porta livre; encerra somente o filho criado aqui."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    root = Path(__file__).resolve().parent
    # Mesmo isolamento de ambiente usado pelo SDK stdio; nunca copiar os.environ.
    from mcp.client.stdio import get_default_environment
    env = {**get_default_environment(), "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
    process = subprocess.Popen([sys.executable, str(root / "mcp_server.py"), "--http", "--port", str(port)],
                               cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        deadline = time.monotonic() + 30
        while True:
            if process.poll() is not None:
                raise RuntimeError("HTTP server exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("HTTP server startup")
                time.sleep(.05)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


async def diagnose(action="discover", transport="stdio", name="get_order", arguments=None, emit=None):
    if action == "compare":
        return await compare_demo_servers(emit)
    if action == "timeout":
        return await request_mcp("call", "get_delivery_status", {"shipment_id": "E100"},
                                 timeout_s=.5, delay_s=1.5, emit=emit)
    return await request_mcp(action, name, arguments or {}, transport=transport, emit=emit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--action", choices=["discover", "call", "resource", "timeout"], default="discover")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--tool", default="get_order")
    parser.add_argument("--arguments", default='{"order_id":"P100"}')
    options = parser.parse_args()
    from config import load_environment
    load_environment()
    result = asyncio.run(diagnose("compare" if options.compare else options.action, options.transport,
                                  options.tool, json.loads(options.arguments)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
