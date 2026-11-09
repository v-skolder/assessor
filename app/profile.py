"""Persistência e indexação do perfil financeiro do usuário."""

from datetime import datetime, timezone
from uuid import uuid4

from pymongo import MongoClient, ReturnDocument
from qdrant_client import models

from app.config import MONGODB_URI
from app.vectorstore import (
    COLLECTION_PERFIL_RESTRICOES,
    EMBEDDING_DIM,
    gerar_embedding,
    gerar_embeddings_batch,
    qdrant,
)

_mongo = MongoClient(MONGODB_URI, connect=False)
col_perfis = _mongo["assessor"]["perfis"]


class PerfilIndexacaoError(RuntimeError):
    """Indica indisponibilidade ao atualizar o índice semântico do perfil."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _garantir_collection_restricoes() -> None:
    if not qdrant.collection_exists(COLLECTION_PERFIL_RESTRICOES):
        qdrant.create_collection(
            collection_name=COLLECTION_PERFIL_RESTRICOES,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIM,
                distance=models.Distance.COSINE,
            ),
        )


def _pontos_restricoes(
    user_id: str, versao_indice: str, restricoes: list[str]
) -> list[models.PointStruct]:
    vetores = gerar_embeddings_batch(restricoes)
    return [
        models.PointStruct(
            id=str(uuid4()),
            vector=vetor,
            payload={
                "user_id": user_id,
                "versao_indice": versao_indice,
                "restricao": restricao,
                "ordem": ordem,
            },
        )
        for ordem, (restricao, vetor) in enumerate(zip(restricoes, vetores), start=1)
    ]


def _remover_versao_indice(user_id: str, versao_indice: str | None) -> None:
    if not versao_indice:
        return
    qdrant.delete(
        collection_name=COLLECTION_PERFIL_RESTRICOES,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id),
                    ),
                    models.FieldCondition(
                        key="versao_indice",
                        match=models.MatchValue(value=versao_indice),
                    ),
                ]
            )
        ),
        wait=True,
    )


def _perfil_publico(perfil: dict) -> dict:
    return {
        "user_id": perfil["user_id"],
        "renda_mensal": perfil["renda_mensal"],
        "gasto_fixo_mensal": perfil["gasto_fixo_mensal"],
        "horizonte_meses": perfil["horizonte_meses"],
        "perfil_investidor": perfil["perfil_investidor"],
        "restricoes": perfil["restricoes"],
    }


def salvar_perfil(dados: dict) -> dict:
    """Atualiza o perfil oficial e substitui seu conjunto de vetores no Qdrant."""
    col_perfis.create_index("user_id", unique=True)
    anterior = col_perfis.find_one({"user_id": dados["user_id"]})
    versao_anterior = anterior.get("versao_indice") if anterior else None
    versao_nova = str(uuid4())

    try:
        _garantir_collection_restricoes()
        qdrant.upsert(
            collection_name=COLLECTION_PERFIL_RESTRICOES,
            points=_pontos_restricoes(
                dados["user_id"], versao_nova, dados["restricoes"]
            ),
            wait=True,
        )
    except Exception as erro:
        raise PerfilIndexacaoError("Não foi possível indexar as restrições.") from erro

    agora = _agora()
    try:
        perfil = col_perfis.find_one_and_update(
            {"user_id": dados["user_id"]},
            {
                "$set": {
                    **dados,
                    "versao_indice": versao_nova,
                    "atualizado_em": agora,
                },
                "$setOnInsert": {"criado_em": agora},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except Exception:
        # O Mongo é a fonte de verdade. Não deixe vetores órfãos se ele falhar.
        try:
            _remover_versao_indice(dados["user_id"], versao_nova)
        except Exception:
            pass
        raise

    try:
        _remover_versao_indice(dados["user_id"], versao_anterior)
    except Exception as erro:
        raise PerfilIndexacaoError(
            "Perfil salvo, mas não foi possível limpar o índice anterior."
        ) from erro

    return _perfil_publico(perfil)


def buscar_perfil_com_restricoes(
    user_id: str, consulta: str, limite: int = 5
) -> tuple[dict | None, list[str]]:
    """Busca o perfil oficial e as restrições semanticamente mais relacionadas."""
    perfil = col_perfis.find_one({"user_id": user_id})
    if not perfil:
        return None, []

    resposta = qdrant.query_points(
        collection_name=COLLECTION_PERFIL_RESTRICOES,
        query=gerar_embedding(consulta),
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id),
                ),
                models.FieldCondition(
                    key="versao_indice",
                    match=models.MatchValue(value=perfil["versao_indice"]),
                ),
            ]
        ),
        limit=min(limite, len(perfil["restricoes"])),
    )
    restricoes = [ponto.payload["restricao"] for ponto in resposta.points]
    return _perfil_publico(perfil), restricoes
