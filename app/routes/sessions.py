from fastapi import APIRouter

from app.controllers.session_controller import (
    abrir_sessao,
    criar_sessao,
    encerrar_sessao_explicitamente,
    fechar_sessao,
    obter_historico,
)
from app.models.schemas import HistoryResponse, SessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
def create_session() -> SessionResponse:
    return criar_sessao()


@router.delete("/{session_id}", response_model=SessionResponse)
def close_session(session_id: str) -> SessionResponse:
    return fechar_sessao(session_id)


@router.get("/{session_id}/historico", response_model=HistoryResponse)
def history(session_id: str) -> HistoryResponse:
    return obter_historico(session_id)


@router.post("/{session_id}/iniciar", response_model=SessionResponse)
def iniciar(session_id: str) -> SessionResponse:
    """
    Abre uma sessão explicitamente.

    Opcional na prática — salvar_mensagem() já abre a sessão sozinho na primeira
    mensagem. Existe para o caso de você querer registrar o acesso mesmo que o
    usuário não chegue a perguntar nada.
    """
    return abrir_sessao(session_id)


@router.post("/{session_id}/encerrar", response_model=SessionResponse)
def encerrar(session_id: str) -> SessionResponse:
    """
    Encerra a sessão: gera o resumo via LLM e grava no documento.

    É este resumo que a tool `buscar_historico` vai encontrar depois. Sem passar
    por aqui, a conversa fica guardada no Mongo mas invisível para a memória de
    longo prazo — porque recuperar_historico() filtra por resumo não-vazio.

    Devolve resumo=None (e não erro) quando não havia nada a encerrar: sessão
    inexistente ou sem nenhuma mensagem. Encerrar duas vezes é inofensivo.

    Atenção ao custo: esta rota faz uma chamada de LLM para gerar o resumo.
    Não a acione a cada mensagem — só ao fim da conversa.
    """
    return encerrar_sessao_explicitamente(session_id)
