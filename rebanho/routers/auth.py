import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from database import supabase

router = APIRouter()

_TOKEN_COOKIE = "cb_token"
_TTL_HORAS = 24 * 30  # 30 dias — sessão longa pra vaqueiro em campo


def _hash(senha: str) -> str:
    return hashlib.sha256(senha.encode()).hexdigest()


def _novo_token() -> str:
    return uuid.uuid4().hex


def _expira() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=_TTL_HORAS)).isoformat()


def get_usuario_atual(request: Request, db=None):
    token = request.cookies.get(_TOKEN_COOKIE) or request.headers.get("X-Auth-Token")
    if not token:
        return None
    # JOIN via PostgREST: 'usuarios(*)' depende da FK
    # sessoes.usuario_id -> usuarios(id). Se a FK ou nome da tabela
    # mudarem, o JOIN retorna None silenciosamente — ajustar aqui.
    rows = supabase.table("sessoes").select("*,usuarios(*)").eq("token", token).limit(1).execute().data
    if not rows:
        return None
    sessao = rows[0]
    if datetime.fromisoformat(sessao["expira_em"]) < datetime.now(timezone.utc):
        supabase.table("sessoes").delete().eq("token", token).execute()
        return None
    usuario = sessao.get("usuarios")
    if not usuario or not usuario.get("ativo"):
        return None
    return usuario


def require_gestor(request: Request, db=None):
    u = get_usuario_atual(request)
    if not u or u["perfil"] != "GESTOR":
        raise HTTPException(status_code=403, detail="Acesso restrito ao perfil GESTOR")
    return u


@router.post("/login")
def login(payload: dict, response: Response):
    login_str = (payload.get("login") or "").strip().lower()
    senha = payload.get("senha") or ""
    rows = supabase.table("usuarios").select("*").eq("login", login_str).eq("ativo", True).limit(1).execute().data
    if not rows or rows[0]["senha_hash"] != _hash(senha):
        raise HTTPException(status_code=401, detail="Login ou senha inválidos")
    u = rows[0]
    token = _novo_token()
    supabase.table("sessoes").insert({
        "token": token, "usuario_id": u["id"], "expira_em": _expira()
    }).execute()
    response.set_cookie(_TOKEN_COOKIE, token, httponly=True, samesite="lax", max_age=_TTL_HORAS * 3600)
    return {"token": token, "perfil": u["perfil"], "nome": u["nome"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(_TOKEN_COOKIE) or request.headers.get("X-Auth-Token")
    if token:
        supabase.table("sessoes").delete().eq("token", token).execute()
    response.delete_cookie(_TOKEN_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    u = get_usuario_atual(request)
    if not u:
        return {"autenticado": False}
    return {"autenticado": True, "perfil": u["perfil"], "nome": u["nome"], "login": u["login"]}


def seed_usuarios(db=None):
    rows = supabase.table("usuarios").select("id").limit(1).execute().data
    if rows:
        return
    supabase.table("usuarios").insert([
        {"login": "gestor", "senha_hash": _hash("1234"), "nome": "Gestor", "perfil": "GESTOR", "ativo": True},
        {"login": "campo", "senha_hash": _hash("1234"), "nome": "Funcionário Campo", "perfil": "FUNCIONARIO", "ativo": True},
    ]).execute()
