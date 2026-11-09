from uuid import uuid4

from app.memory import encerrar_sessao, iniciar_sessao, recuperar_mensagens
from app.models.schemas import HistoryResponse, SessionResponse


def criar_sessao() -> SessionResponse:
    session_id = str(uuid4())
    iniciar_sessao(session_id)
    return SessionResponse(session_id=session_id)


def fechar_sessao(session_id: str) -> SessionResponse:
    return SessionResponse(session_id=session_id, resumo=encerrar_sessao(session_id))


def encerrar_sessao_explicitamente(session_id: str) -> SessionResponse:
    resumo = encerrar_sessao(session_id)
    return SessionResponse(session_id=session_id, resumo=resumo or None)


def obter_historico(session_id: str) -> HistoryResponse:
    return HistoryResponse(
        session_id=session_id,
        mensagens=recuperar_mensagens(session_id),
    )


def abrir_sessao(session_id: str) -> SessionResponse:
    iniciar_sessao(session_id)
    return SessionResponse(session_id=session_id, resumo=None)
