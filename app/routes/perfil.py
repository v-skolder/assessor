from fastapi import APIRouter, HTTPException, status

from app.models.schemas import PerfilRequest, PerfilResponse
from app.profile import PerfilIndexacaoError, salvar_perfil

router = APIRouter(tags=["perfil"])


@router.post("/perfil", response_model=PerfilResponse)
def criar_ou_atualizar_perfil(requisicao: PerfilRequest) -> PerfilResponse:
    try:
        perfil = salvar_perfil(requisicao.model_dump())
    except PerfilIndexacaoError as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(erro),
        ) from erro
    return PerfilResponse(**perfil)
