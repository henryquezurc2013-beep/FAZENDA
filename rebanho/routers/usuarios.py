"""CRUD de usuários — acesso restrito a perfil GESTOR.

Senhas armazenadas como SHA-256 hexdigest (consistente com auth.py).
Não usa bcrypt nesta fase — refator de segurança fica pra sessão dedicada.
"""
from fastapi import APIRouter, HTTPException, Request

from database import supabase
from routers.auth import _hash

router = APIRouter()

_PERFIS_VALIDOS = ("GESTOR", "FUNCIONARIO")


def _exigir_gestor(request: Request):
    usuario = getattr(request.state, "usuario_atual", None)
    if not usuario or usuario.get("perfil") != "GESTOR":
        raise HTTPException(status_code=403, detail="Acesso restrito a GESTOR")
    return usuario


def _to_out(u: dict) -> dict:
    """Remove senha_hash da resposta."""
    return {k: v for k, v in u.items() if k != "senha_hash"}


@router.get("")
def listar(request: Request):
    _exigir_gestor(request)
    rows = supabase.table("usuarios").select("*").order("criado_em", desc=True).execute().data
    return [_to_out(u) for u in rows]


@router.post("", status_code=201)
def criar(request: Request, body: dict):
    _exigir_gestor(request)
    login = (body.get("login") or "").strip().lower()
    senha = body.get("senha") or ""
    nome = (body.get("nome") or "").strip()
    perfil = (body.get("perfil") or "FUNCIONARIO").upper()

    if not login or not senha or not nome:
        raise HTTPException(400, "Campos obrigatórios: login, senha, nome")
    if perfil not in _PERFIS_VALIDOS:
        raise HTTPException(400, f"Perfil deve ser um de: {_PERFIS_VALIDOS}")

    # Login deve ser único (case-insensitive)
    existing = supabase.table("usuarios").select("id").eq("login", login).limit(1).execute().data
    if existing:
        raise HTTPException(409, "Login já existe")

    novo = {
        "login": login,
        "senha_hash": _hash(senha),
        "nome": nome,
        "perfil": perfil,
        "ativo": True,
    }
    result = supabase.table("usuarios").insert(novo).execute().data[0]
    return _to_out(result)


@router.put("/{usuario_id}")
def editar(usuario_id: int, request: Request, body: dict):
    _exigir_gestor(request)
    rows = supabase.table("usuarios").select("*").eq("id", usuario_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Usuário não encontrado")

    update = {}
    if "nome" in body:
        nome = (body.get("nome") or "").strip()
        if not nome:
            raise HTTPException(400, "Nome não pode ser vazio")
        update["nome"] = nome
    if "perfil" in body:
        perfil = (body.get("perfil") or "").upper()
        if perfil not in _PERFIS_VALIDOS:
            raise HTTPException(400, f"Perfil deve ser um de: {_PERFIS_VALIDOS}")
        update["perfil"] = perfil
    if "senha" in body and body["senha"]:
        update["senha_hash"] = _hash(body["senha"])

    if not update:
        return _to_out(rows[0])

    supabase.table("usuarios").update(update).eq("id", usuario_id).execute()
    result = supabase.table("usuarios").select("*").eq("id", usuario_id).limit(1).execute().data[0]
    return _to_out(result)


@router.patch("/{usuario_id}/ativo")
def alternar_ativo(usuario_id: int, request: Request, body: dict):
    gestor = _exigir_gestor(request)
    if gestor["id"] == usuario_id:
        raise HTTPException(400, "Você não pode desativar a si mesmo")

    rows = supabase.table("usuarios").select("*").eq("id", usuario_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Usuário não encontrado")

    novo_ativo = bool(body.get("ativo", True))
    supabase.table("usuarios").update({"ativo": novo_ativo}).eq("id", usuario_id).execute()

    # Se desativando, derruba todas as sessões ativas desse usuário
    if not novo_ativo:
        supabase.table("sessoes").delete().eq("usuario_id", usuario_id).execute()

    result = supabase.table("usuarios").select("*").eq("id", usuario_id).limit(1).execute().data[0]
    return _to_out(result)
