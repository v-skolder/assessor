import json

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.profile import buscar_perfil_com_restricoes


@tool
def consultar_perfil_financeiro(pergunta: str, config: RunnableConfig) -> str:
    """Consulta o perfil financeiro cadastrado para aconselhar o usuário.

    Use para recomendações sobre orçamento, poupança, metas, prazo ou investimentos.
    O usuário é identificado automaticamente pelo contexto da conversa; nunca peça
    nem invente um user_id.
    """
    configuravel = (config or {}).get("configurable", {})
    user_id = configuravel.get("user_id") or configuravel.get("thread_id")
    if not user_id:
        return "Não foi possível identificar o usuário para consultar o perfil financeiro."

    try:
        perfil, restricoes = buscar_perfil_com_restricoes(user_id, pergunta)
    except Exception:
        return "Não foi possível consultar o perfil financeiro neste momento."

    if not perfil:
        return (
            "Nenhum perfil financeiro cadastrado. Oriente o usuário a preencher "
            "o cadastro em /perfil.html; não invente renda, gastos ou restrições."
        )

    return json.dumps(
        {
            "perfil": perfil,
            "restricoes_relevantes": restricoes,
        },
        ensure_ascii=False,
    )


TOOLS_PERFIL = [consultar_perfil_financeiro]
