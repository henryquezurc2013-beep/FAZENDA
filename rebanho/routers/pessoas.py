import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from database import supabase
from schemas import PessoaCreate

router = APIRouter()

_PREFIXO = {"CLIENTE": "CLI", "FORNECEDOR": "FOR"}


def _gerar_codigo(tipo: str) -> str:
    prefixo = _PREFIXO.get(tipo.upper())
    if not prefixo:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: {tipo}")
    existentes = supabase.table("pessoas").select("codigo").ilike("tipo", tipo).execute().data
    maior = 0
    for row in existentes:
        codigo = row.get("codigo") or ""
        m = re.match(rf"^{prefixo}-(\d+)$", codigo, re.IGNORECASE)
        if m:
            maior = max(maior, int(m.group(1)))
    novo = f"{prefixo}-{str(maior + 1).zfill(3)}"
    conflito = supabase.table("pessoas").select("id").eq("codigo", novo).limit(1).execute().data
    if conflito:
        raise HTTPException(status_code=500, detail=f"Conflito de código gerado: {novo}")
    return novo


@router.get("/clientes")
def listar_clientes():
    return supabase.table("pessoas").select("*").ilike("tipo", "CLIENTE").order("nome").execute().data


@router.get("/fornecedores")
def listar_fornecedores():
    return supabase.table("pessoas").select("*").ilike("tipo", "FORNECEDOR").order("nome").execute().data


@router.get("")
def listar_pessoas(tipo: Optional[str] = Query(None)):
    q = supabase.table("pessoas").select("*")
    if tipo:
        q = q.ilike("tipo", tipo)
    return q.order("nome").execute().data


@router.post("", status_code=201)
def criar_pessoa(payload: PessoaCreate):
    if not payload.tipo or not payload.nome:
        raise HTTPException(status_code=400, detail="Campos obrigatórios: tipo, nome")
    codigo = _gerar_codigo(payload.tipo)
    data = payload.model_dump()
    data["codigo"] = codigo
    return supabase.table("pessoas").insert(data).execute().data[0]


@router.put("/{id}")
def atualizar_pessoa(id: int, payload: PessoaCreate):
    rows = supabase.table("pessoas").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if k != "codigo"}
    supabase.table("pessoas").update(update_data).eq("id", id).execute()
    return supabase.table("pessoas").select("*").eq("id", id).limit(1).execute().data[0]


@router.delete("/{id}")
def deletar_pessoa(id: int):
    rows = supabase.table("pessoas").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    supabase.table("pessoas").delete().eq("id", id).execute()
    return {"mensagem": "Pessoa removida com sucesso"}
