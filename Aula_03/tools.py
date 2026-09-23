"""Dados operacionais e as três ferramentas da Aula 02."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "dados"


def _read_json(name: str) -> dict:
    with (DATA_DIR / name).open(encoding="utf-8") as file:
        return json.load(file)


ORDERS = _read_json("orders.json")
SHIPMENTS = _read_json("shipments.json")


def get_order(order_id: str) -> dict:
    """Consulta um pedido Pxxx informado pelo usuário, sem inferir identificadores."""
    return deepcopy(ORDERS.get(order_id, {"error": "order_not_found"}))


def get_delivery_status(shipment_id: str) -> dict:
    """Consulta a remessa Exxx retornada por get_order; não recebe um pedido."""
    return deepcopy(SHIPMENTS.get(shipment_id, {"error": "shipment_not_found"}))


def get_resolution_options(order_id: str) -> dict:
    """Retorna opções condicionais; não executa chamado, reembolso ou outra ação."""
    if order_id not in ORDERS:
        return {"error": "order_not_found"}
    return {
        "rule_id": "R01",
        "rule_version": "2026-09-lab",
        "options": [
            {"action": "informar", "available": True, "requires": "fatos verificados"},
            {
                "action": "ticket",
                "available": True,
                "requires": "solicitação explícita e autorização da aplicação",
            },
        ],
        "refund_available": False,
    }
