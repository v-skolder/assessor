"""Ferramentas da agenda local, compartilhadas pelo chat e pelo servidor MCP."""

from datetime import date, datetime, timedelta
from typing import Optional

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.escritas import executar_escrita
from app.tools.db import get_conn


class AddEventArgs(BaseModel):
    title: str = Field(..., min_length=1, description="Título do compromisso.")
    source_text: str = Field(..., description="Pedido original do usuário.")
    start_time: str = Field(..., description="Início ISO 8601 com fuso horário.")
    end_time: Optional[str] = Field(None, description="Fim ISO 8601 com fuso horário.")
    location: Optional[str] = Field(None, description="Local do compromisso.")
    notes: Optional[str] = Field(None, description="Observações.")


def _aplicar_add_event(cur, op: dict) -> dict:
    """Executa o INSERT do compromisso."""
    cur.execute("""
        INSERT INTO events (title, start_time, end_time, location, notes, source_text)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, start_time, end_time
    """, (op["title"], op["start_time"], op["end_time"], op.get("location"), op.get("notes"), op["source_text"]))
    event_id, inicio_db, fim_db = cur.fetchone()
    return {"status": "ok", "id": event_id, "title": op["title"],
            "start_time": inicio_db.isoformat(),
            "end_time": fim_db.isoformat() if fim_db else None}


@tool("add_event", args_schema=AddEventArgs)
def add_event(title: str, source_text: str, start_time: str,
              end_time: Optional[str] = None, location: Optional[str] = None,
              notes: Optional[str] = None, *, config: RunnableConfig) -> dict:
    """Registra um compromisso na tabela events do Postgres."""
    try:
        inicio = datetime.fromisoformat(start_time)
        fim = datetime.fromisoformat(end_time) if end_time else inicio + timedelta(hours=1)
        if inicio.tzinfo is None or fim.tzinfo is None:
            return {"status": "error", "message": "Informe horários com fuso horário."}
        if fim <= inicio:
            return {"status": "error", "message": "O fim deve ser posterior ao início."}
    except ValueError:
        return {"status": "error", "message": "Horário inválido; use ISO 8601."}

    return executar_escrita(config, _aplicar_add_event, {
        "title": title, "start_time": inicio.isoformat(), "end_time": fim.isoformat(),
        "location": location, "notes": notes, "source_text": source_text,
    })


class QueryEventsArgs(BaseModel):
    text: Optional[str] = Field(None, description="Busca em título, local, notas e pedido original.")
    date_local: Optional[str] = Field(None, description="Dia YYYY-MM-DD em America/Sao_Paulo.")
    date_from_local: Optional[str] = Field(None, description="Primeiro dia YYYY-MM-DD, inclusive.")
    date_to_local: Optional[str] = Field(None, description="Último dia YYYY-MM-DD, inclusive.")
    limit: int = Field(20, ge=1, le=200)


@tool("query_events", args_schema=QueryEventsArgs)
def query_events(text: Optional[str] = None, date_local: Optional[str] = None,
                 date_from_local: Optional[str] = None, date_to_local: Optional[str] = None,
                 limit: int = 20) -> dict:
    """Consulta compromissos no Postgres antes de afirmar disponibilidade."""
    if date_local and (date_from_local or date_to_local):
        return {"status": "error", "message": "Use date_local ou um intervalo, não ambos."}
    try:
        for value in (date_local, date_from_local, date_to_local):
            if value:
                date.fromisoformat(value)
        if date_from_local and date_to_local and date_from_local > date_to_local:
            return {"status": "error", "message": "Intervalo de datas invertido."}
    except ValueError:
        return {"status": "error", "message": "Data inválida; use YYYY-MM-DD."}

    clauses = []
    params = {"limit": limit}
    if text:
        clauses.append("(title ILIKE %(text)s OR location ILIKE %(text)s OR notes ILIKE %(text)s OR source_text ILIKE %(text)s)")
        params["text"] = f"%{text}%"
    first = date_local or date_from_local
    last = date_local or date_to_local
    if first:
        clauses.append("start_time >= (%(first)s::date AT TIME ZONE 'America/Sao_Paulo')")
        params["first"] = first
    if last:
        clauses.append("start_time < ((%(last)s::date + INTERVAL '1 day') AT TIME ZONE 'America/Sao_Paulo')")
        params["last"] = last
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, title, start_time, end_time, location, notes, source_text, recorded_at
                FROM events {where} ORDER BY start_time ASC LIMIT %(limit)s
            """, params)
            rows = cur.fetchall()
        keys = ("id", "title", "start_time", "end_time", "location", "notes", "source_text", "recorded_at")
        results = [dict(zip(keys, (v.isoformat() if isinstance(v, datetime) else v for v in row))) for row in rows]
        return {"status": "ok", "count": len(results), "results": results}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        if conn:
            conn.close()


TOOLS_AGENDA = [add_event, query_events]