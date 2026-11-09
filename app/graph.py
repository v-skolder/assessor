import operator
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, MessagesState, StateGraph

from app.agents import agenda_app, faq_app, financeiro_app, orquestrador_app, router_app
from app.escritas import descartar
from app.guardrail import anonimizar_entrada, guardrail_entrada, guardrail_saida
from app.juiz import no_juiz
from app.memory import salvar_mensagem
from app.observabilidade import abrir_turno, fechar_turno, status_do_estado

class Estado(MessagesState):
    session_id: str
    user_id: str
    agentes_chamados: Annotated[list[str], operator.add]
    rota: str
    mapa_pii: dict[str, str]
    entrada_aprovou: bool
    saida_especialista: str
    resposta_final: str
    saida_aprovou: bool


def _texto(mensagem) -> str:
    return mensagem.content if hasattr(mensagem, "content") else mensagem.get("content", "")


def no_guardrail_entrada(estado: Estado) -> dict:
    verificacao = guardrail_entrada(_texto(estado["messages"][-1]))
    if verificacao["bloqueado"]:
        return {
            "entrada_aprovou": False,
            "resposta_final": f"[BLOQUEADO] {verificacao['mensagem']}",
            "agentes_chamados": ["guardrail_entrada"],
        }
    return {"entrada_aprovou": True, "agentes_chamados": ["guardrail_entrada"]}


def decidir_pos_guardrail_entrada(estado: Estado) -> str:
    return "saida" if not estado.get("entrada_aprovou") else "roteador"


def no_roteador(estado: Estado) -> dict:
    saida = router_app.invoke(
        {"messages": estado["messages"]},
        config={
            "configurable": {
                "thread_id": estado["session_id"],
                "user_id": estado["user_id"],
            }
        },
    )
    texto = _texto(saida["messages"][-1])
    rota = "fim"
    for linha in texto.splitlines():
        if linha.startswith("ROUTE="):
            rota = linha.split("=", 1)[1].strip()
            break
    return {
        "agentes_chamados": ["roteador"],
        "rota": rota,
        "messages": [{"role": "system", "content": texto}],
    }


def no_financeiro(estado: Estado, config: RunnableConfig) -> dict:
    saida = financeiro_app.invoke(
        {"messages": estado["messages"]},
        config={
            "configurable": {
                "thread_id": estado["session_id"],
                "user_id": estado["user_id"],
                "turno_id": config["configurable"].get("turno_id"),
            }
        },
    )
    return {
        "saida_especialista": _texto(saida["messages"][-1]),
        "agentes_chamados": ["financeiro"],
        "messages": saida["messages"][len(estado["messages"]):],
    }


def no_agenda(estado: Estado, config: RunnableConfig) -> dict:
    saida = agenda_app.invoke(
        {"messages": estado["messages"]},
        config={
            "configurable": {
                "thread_id": estado["session_id"],
                "user_id": estado["user_id"],
                "turno_id": config["configurable"].get("turno_id"),
            }
        },
    )
    return {
        "saida_especialista": _texto(saida["messages"][-1]),
        "agentes_chamados": ["agenda"],
        "messages": saida["messages"][len(estado["messages"]):],
    }


def no_faq(estado: Estado) -> dict:
    saida = faq_app.invoke(
        {"messages": estado["messages"]},
        config={
            "configurable": {
                "thread_id": estado["session_id"],
                "user_id": estado["user_id"],
            }
        },
    )
    texto = _texto(saida["messages"][-1])
    return {
        "saida_especialista": texto,
        "agentes_chamados": ["faq"],
        "messages": [{"role": "assistant", "content": texto}],
    }


def no_orquestrador(estado: Estado, config: RunnableConfig) -> dict:
    # Pega a última resposta do especialista (última AIMessage com conteúdo)
    ultima_especialista = ""
    for mensagem in reversed(estado["messages"]):
        if mensagem.type == "ai" and mensagem.content:
            ultima_especialista = mensagem.content
            break
    # config segue o mesmo motivo do roteador: sem ele, o modelo deste nó
    # não herda o metadata do grafo (e o registro de observabilidade perde o nó).
    saida = orquestrador_app.invoke({
        "messages": [{"role": "human", "content": ultima_especialista}]
    }, config=config)

    return {
        "agentes_chamados": ["orquestrador"],
        "messages":        [{"role": "assistant", "content": saida["messages"][-1].text}]
    }


def decidir_especialista(estado: Estado) -> str:
    rota = estado.get("rota", "fim")
    return rota if rota in {"financeiro", "agenda", "faq"} else "saida"


def no_guardrail_saida(estado: Estado) -> dict:
    if not estado.get("entrada_aprovou"):
        return {"agentes_chamados": ["guardrail_saida"]}
    resposta = _texto(estado["messages"][-1])
    revisada = guardrail_saida(resposta, estado.get("mapa_pii", {}), restaurar_pii=False)
    return {
        "resposta_final": revisada["conteudo"],
        "agentes_chamados": ["guardrail_saida"],
    }


grafo = StateGraph(Estado)
grafo.add_node("guardrail_entrada", no_guardrail_entrada)
grafo.add_node("roteador", no_roteador)
grafo.add_node("financeiro", no_financeiro)
grafo.add_node("agenda", no_agenda)
grafo.add_node("faq", no_faq)
grafo.add_node("orquestrador", no_orquestrador)
grafo.add_node("guardrail_saida", no_guardrail_saida)
grafo.add_node("juiz", no_juiz)
grafo.set_entry_point("guardrail_entrada")
grafo.add_conditional_edges(
    "guardrail_entrada",
    decidir_pos_guardrail_entrada,
    {"roteador": "roteador", "saida": "guardrail_saida"},
)
grafo.add_conditional_edges(
    "roteador",
    decidir_especialista,
    {
        "financeiro": "financeiro",
        "agenda": "agenda",
        "faq": "faq",
        "saida": "guardrail_saida",
    },
)

grafo.add_edge("financeiro",      "orquestrador")
grafo.add_edge("agenda",          "orquestrador")
grafo.add_edge("orquestrador",    "guardrail_saida")
grafo.add_edge("guardrail_saida", "juiz")
grafo.add_edge("faq",             "juiz")
grafo.add_edge("juiz",            END)

fluxo_agentes = grafo.compile(checkpointer=MemorySaver())


def executar_fluxo(
    pergunta_usuario: str, session_id: str, user_id: str = "usuario_teste"
) -> tuple[str, list[str]]:
    pergunta_usuario_anonimizado, _ = anonimizar_entrada(pergunta_usuario)
    estado_inicial = {
        "messages":         [{"role": "human", "content": pergunta_usuario}],
        "agentes_chamados": [],
        "rota":             "",
        "mapa_pii":         {},
        "session_id":       session_id,
        "user_id":          user_id,
        "entrada_aprovou":  False,
        "saida_aprovou":     False,
    }

    turno_id = abrir_turno()
    status = "erro"
    rota = ""
    try:
        config = {"configurable": {"thread_id": session_id, "user_id": user_id, "turno_id": turno_id}}
        anteriores = len(fluxo_agentes.get_state(config).values.get("agentes_chamados", []))
        estado_final = fluxo_agentes.invoke(estado_inicial, config=config)
        agentes = estado_final.get("agentes_chamados", [])[anteriores:]

        if not estado_final.get("entrada_aprovou"):
            resposta = estado_final["resposta_final"]
        else:
            resposta = estado_final["messages"][-1].text

        status = status_do_estado({"bloqueado": not estado_final.get("entrada_aprovou"), "agentes_chamados": agentes})
        rota = estado_final.get("rota") or ""
        try:
            salvar_mensagem(session_id, "human",     pergunta_usuario_anonimizado, user_id=user_id)
            salvar_mensagem(session_id, "assistant", resposta, user_id=user_id)
        except Exception as exc:
            print(f"[memoria] erro {exc}")
            status = "erro"
        return resposta, list(dict.fromkeys(agentes))
    finally:
        descartar(turno_id)
        fechar_turno(turno_id, session_id=session_id, rota=rota, status=status)