
import pytest
from pydantic import ValidationError

from app.models.schemas import ChatRequest, PerfilRequest


__all__ = [
    "test_chat_request_accepts_valid_payload",
    "test_chat_request_rejects_empty_question",
    "test_perfil_request_accepts_valid_payload_and_trims_restrictions",
    "test_perfil_request_rejects_expenses_equal_to_income",
    "test_perfil_request_rejects_empty_restriction",
    "test_perfil_request_rejects_unknown_investor_profile",
]


def test_chat_request_accepts_valid_payload():
    requisicao = ChatRequest(
        session_id="sessao-123",
        pergunta="Quanto gastei este mês?",
    )

    assert requisicao.user_id == "usuario_teste"
    assert requisicao.pergunta == "Quanto gastei este mês?"


def test_chat_request_rejects_empty_question():
    with pytest.raises(ValidationError):
        ChatRequest(session_id="sessao-123", pergunta="")


def test_perfil_request_accepts_valid_payload_and_trims_restrictions():
    perfil = PerfilRequest(
        user_id="usuario-123",
        renda_mensal=5000,
        gasto_fixo_mensal=2000,
        horizonte_meses=12,
        perfil_investidor="moderado",
        restricoes=["  evitar risco alto  "],
    )

    assert perfil.restricoes == ["evitar risco alto"]


def test_perfil_request_rejects_expenses_equal_to_income():
    with pytest.raises(ValidationError):
        PerfilRequest(
            user_id="usuario-123",
            renda_mensal=5000,
            gasto_fixo_mensal=5000,
            horizonte_meses=12,
            perfil_investidor="moderado",
            restricoes=["evitar risco alto"],
        )


def test_perfil_request_rejects_empty_restriction():
    with pytest.raises(ValidationError):
        PerfilRequest(
            user_id="usuario-123",
            renda_mensal=5000,
            gasto_fixo_mensal=2000,
            horizonte_meses=12,
            perfil_investidor="moderado",
            restricoes=["   "],
        )


def test_perfil_request_rejects_unknown_investor_profile():
    with pytest.raises(ValidationError):
        PerfilRequest(
            user_id="usuario-123",
            renda_mensal=5000,
            gasto_fixo_mensal=2000,
            horizonte_meses=12,
            perfil_investidor="agressivo",
            restricoes=["evitar risco alto"],
        )
