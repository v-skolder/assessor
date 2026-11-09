
"""Escrita adiada do turno: a tool só enfileira em memória, a gravação espera o juiz."""

import threading
from typing import Any, Callable, Optional

from langchain_core.runnables import RunnableConfig

from app.tools.db import get_conn


__all__ = \
[
    "FRASE_DESCARTE",
    "FRASE_FALHA_GRAVACAO",
    "adiar_externa",
    "confirmar",
    "descartar",
    "executar_escrita"
]


FRASE_DESCARTE = "Por isso, nada deste pedido foi gravado. Pode repetir com mais detalhes?"
FRASE_FALHA_GRAVACAO = "Não consegui gravar este pedido, então nada foi registrado. Tente de novo em instantes."

_trava = threading.Lock()
_pendentes: dict[str, list[tuple[str, Callable, dict]]] = {}


def _turno(config: Optional[RunnableConfig]) -> Optional[str]:
    return ((config or {}).get("configurable") or {}).get("turno_id")


def _registrar(turno_id: str, tipo: str, aplicar: Callable, operacao: dict) -> None:
    with _trava:
        _pendentes.setdefault(turno_id, []).append((tipo, aplicar, operacao))


def _retirar(turno_id: Optional[str]) -> list[tuple[str, Callable, dict]]:
    with _trava:
        return _pendentes.pop(turno_id, []) if turno_id else []


def executar_escrita(config: Optional[RunnableConfig], aplicar: Callable[[Any, dict], dict], operacao: dict) -> dict:
    """
    Dentro de um turno, só guarda a operação em memória para o juiz autorizar, sem tocar no
    banco; fora de um turno (ex.: servidor MCP), grava na hora.
    """
    turno_id = _turno(config)
    if turno_id:
        _registrar(turno_id, "postgres", aplicar, operacao)
        return {"status": "ok", "gravacao": "pendente_ate_aprovacao", **{k: v for k, v in operacao.items() if v is not None}}
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            resultado = aplicar(cur, operacao)
        if resultado.get("status") == "ok":
            conn.commit()
        else:
            conn.rollback()
        return resultado
    except Exception as exc:
        if conn:
            conn.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        if conn:
            conn.close()


def adiar_externa(config: Optional[RunnableConfig], aplicar: Callable[[dict], dict], operacao: dict) -> Optional[dict]:
    """Guarda um efeito fora do Postgres para depois do commit. Fora de um turno devolve None."""
    turno_id = _turno(config)
    if not turno_id:
        return None
    _registrar(turno_id, "externa", aplicar, operacao)
    return {"status": "ok", **operacao}


def descartar(turno_id: Optional[str]) -> int:
    """Joga fora as escritas pendentes do turno e diz quantas eram."""
    return len(_retirar(turno_id))


def confirmar(turno_id: Optional[str]) -> dict:
    """
    Grava de uma vez, numa transação, as escritas do turno aprovado e só então roda os
    efeitos externos. Devolve o que realmente aconteceu.
    """
    pendentes = _retirar(turno_id)
    banco = [(aplicar, operacao) for tipo, aplicar, operacao in pendentes if tipo == "postgres"]
    externas = [(aplicar, operacao) for tipo, aplicar, operacao in pendentes if tipo == "externa"]
    resultado = {"total": len(pendentes), "banco": "nada", "externas": [], "mensagem": ""}
    if banco:
        conn = None
        try:
            conn = get_conn()
            with conn.cursor() as cur:
                for aplicar, operacao in banco:
                    saida = aplicar(cur, operacao)
                    if saida.get("status") != "ok":
                        raise RuntimeError(saida.get("message") or "escrita recusada pelo banco")
            conn.commit()
            resultado["banco"] = "ok"
        except Exception as exc:
            if conn:
                conn.rollback()
            resultado.update(banco="falhou", mensagem=str(exc))
            return resultado
        finally:
            if conn:
                conn.close()
    for aplicar, operacao in externas:
        try:
            resultado["externas"].append(aplicar(operacao).get("status") == "ok")
        except Exception:
            resultado["externas"].append(False)
    return resultado