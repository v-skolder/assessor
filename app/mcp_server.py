"""Porta MCP stdio para as ferramentas locais do Assessor.AI."""

import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from app.tools.agenda import add_event as _add_event, query_events as _query_events
from app.tools.financeiro import (
    add_transaction as _add_transaction,
    daily_balance as _daily_balance,
    query_transactions as _query_transactions,
    total_balance as _total_balance,
    update_transaction as _update_transaction,
)

mcp = MCPServer(name="assessor-ai", version="1.0.0",
                instructions="Consulta e registro de finanças e compromissos no Postgres local.")
READ = ToolAnnotations(readOnlyHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)


@mcp.tool(name="total_balance", description="Saldo de todo o histórico.", annotations=READ)
def total_balance() -> dict[str, Any]:
    return _total_balance.invoke({"source_text": "Consulta MCP de saldo total"})


@mcp.tool(name="daily_balance", description="Saldo de um dia, mês ou ano.", annotations=READ)
def daily_balance(occurred_at: Optional[str] = None, periodo: str = "dia") -> dict[str, Any]:
    return _daily_balance.invoke({"source_text": "Consulta MCP de saldo", "occurred_at": occurred_at, "periodo": periodo})


@mcp.tool(name="query_transactions", description="Lista transações por tipo e período.", annotations=READ)
def query_transactions(tipo: str, occurred_at: Optional[str] = None) -> dict[str, Any]:
    return _query_transactions.invoke({"source_text": "Consulta MCP de transações", "tipo": tipo, "occurred_at": occurred_at})


@mcp.tool(name="add_transaction", description="Registra uma transação financeira.", annotations=WRITE)
def add_transaction(amount: float, source_text: str, type_name: str,
                    category_name: Optional[str] = None, description: Optional[str] = None,
                    payment_method: Optional[str] = None,
                    occurred_at: Optional[str] = None) -> dict[str, Any]:
    return _add_transaction.invoke({"amount": amount, "source_text": source_text,
                                    "type_name": type_name, "category_name": category_name,
                                    "description": description, "payment_method": payment_method,
                                    "occurred_at": occurred_at})


@mcp.tool(name="update_transaction", description="Atualiza uma transação por id ou texto e data.", annotations=WRITE)
def update_transaction(id: Optional[int] = None, match_text: Optional[str] = None,
                       date_local: Optional[str] = None, amount: Optional[float] = None,
                       type_name: Optional[str] = None, category_name: Optional[str] = None,
                       description: Optional[str] = None, payment_method: Optional[str] = None,
                       occurred_at: Optional[str] = None) -> dict[str, Any]:
    return _update_transaction.invoke({"id": id, "match_text": match_text,
                                       "date_local": date_local, "amount": amount,
                                       "type_name": type_name, "category_name": category_name,
                                       "description": description, "payment_method": payment_method,
                                       "occurred_at": occurred_at})


@mcp.tool(name="query_events", description="Consulta compromissos por texto ou datas locais.", annotations=READ)
def query_events(text: Optional[str] = None, date_local: Optional[str] = None,
                 date_from_local: Optional[str] = None, date_to_local: Optional[str] = None,
                 limit: int = 20) -> dict[str, Any]:
    return _query_events.invoke({"text": text, "date_local": date_local,
                                 "date_from_local": date_from_local,
                                 "date_to_local": date_to_local, "limit": limit})


@mcp.tool(name="add_event", description="Registra um compromisso no Postgres.", annotations=WRITE)
def add_event(title: str, source_text: str, start_time: str,
              end_time: Optional[str] = None, location: Optional[str] = None,
              notes: Optional[str] = None) -> dict[str, Any]:
    return _add_event.invoke({"title": title, "source_text": source_text,
                              "start_time": start_time, "end_time": end_time,
                              "location": location, "notes": notes})


if __name__ == "__main__":
    mcp.run(transport="stdio")
