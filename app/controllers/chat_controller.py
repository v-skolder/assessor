from app.graph import executar_fluxo
from app.models.schemas import ChatRequest, ChatResponse


def responder_chat(requisicao: ChatRequest) -> ChatResponse:
    """Coordena o atendimento sem expor a implementação do fluxo à rota."""
    resposta, agentes_chamados = executar_fluxo(
        requisicao.pergunta,
        requisicao.session_id,
        requisicao.user_id,
    )
    return ChatResponse(resposta=resposta, agentes_chamados=agentes_chamados)
