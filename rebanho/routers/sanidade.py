from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional, List

from database import supabase, get_fazenda_id

router = APIRouter()

# Supabase sanidade columns:
# id, fazenda_id, brinco, data, tipo, produto, dose, via, medico_vet, proxima_data, custo, obs, criado_em

_ALLOWED_FIELDS = {
    "brinco", "data", "tipo", "produto", "dose", "via", "medico_vet",
    "proxima_data", "custo", "obs", "fazenda_id",
}


def _clean(data: dict) -> dict:
    """Map old field names and keep only valid Supabase columns."""
    out = {}
    for k, v in data.items():
        if k == "medicamento":
            out["produto"] = v
        elif k == "classificacao":
            out["tipo"] = v
        elif k == "quantidade":
            out["dose"] = v
        elif k == "via_aplicacao":
            out["via"] = v
        elif k == "data_retorno":
            out["proxima_data"] = v
        elif k == "custo_unit":
            out["custo"] = v
        elif k == "tipo_evento":
            out["tipo"] = v
        elif k in _ALLOWED_FIELDS:
            out[k] = v
    return out


def _normalize(r: dict) -> dict:
    """Add backward-compat aliases for frontend."""
    return {
        **r,
        "medicamento": r.get("produto"),
        "classificacao": r.get("tipo"),
        "quantidade": r.get("dose"),
        "via_aplicacao": r.get("via"),
        "data_retorno": r.get("proxima_data"),
    }


@router.get("")
def listar_sanidade(
    request: Request,
    brinco: Optional[str] = Query(None),
    classificacao: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    fid = get_fazenda_id(request)
    q = supabase.table("sanidade").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    if brinco:
        q = q.ilike("brinco", brinco)
    if classificacao:
        q = q.ilike("tipo", classificacao)
    if data_inicio:
        q = q.gte("data", data_inicio)
    if data_fim:
        q = q.lte("data", data_fim)
    rows = q.order("data", desc=True).execute().data
    return [_normalize(r) for r in rows]


@router.post("", status_code=201)
def criar_sanidade(request: Request, body: dict):
    animal = supabase.table("animais").select("id,fazenda_id").ilike("brinco", body.get("brinco", "")).limit(1).execute().data
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    if not body.get("data"):
        raise HTTPException(status_code=400, detail="Campo obrigatório: data")
    if not (body.get("produto") or body.get("medicamento")):
        raise HTTPException(status_code=400, detail="Campo obrigatório: produto")
    fid = get_fazenda_id(request)
    data = _clean(dict(body))
    data["fazenda_id"] = fid if fid > 0 else (animal[0].get("fazenda_id") or 1)
    result = supabase.table("sanidade").insert(data).execute().data[0]
    return _normalize(result)


@router.post("/grupo")
def criar_sanidade_grupo(request: Request, body: dict):
    fid = get_fazenda_id(request)
    brincos = body.get("brincos", [])
    salvos = 0
    erros: List[str] = []
    for brinco in brincos:
        animal = supabase.table("animais").select("id,brinco,fazenda_id").ilike("brinco", brinco).limit(1).execute().data
        if not animal:
            erros.append(brinco)
            continue
        a = animal[0]
        row_data = _clean({k: v for k, v in body.items() if k != "brincos"})
        row_data["brinco"] = a["brinco"]
        row_data["fazenda_id"] = fid if fid > 0 else (a.get("fazenda_id") or 1)
        supabase.table("sanidade").insert(row_data).execute()
        salvos += 1
    partes = [f"{salvos} registros lançados com sucesso."]
    if erros:
        partes.append(f"{len(erros)} brincos não encontrados: {erros}")
    else:
        partes.append("0 brincos não encontrados.")
    return {"salvos": salvos, "erros": erros, "mensagem": " ".join(partes)}


@router.put("/{id}")
def atualizar_sanidade(id: int, body: dict):
    rows = supabase.table("sanidade").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Registro de sanidade não encontrado")
    update_data = _clean(dict(body))
    supabase.table("sanidade").update(update_data).eq("id", id).execute()
    result = supabase.table("sanidade").select("*").eq("id", id).limit(1).execute().data[0]
    return _normalize(result)


@router.delete("/{id}")
def deletar_sanidade(id: int):
    rows = supabase.table("sanidade").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Registro de sanidade não encontrado")
    supabase.table("sanidade").delete().eq("id", id).execute()
    return {"mensagem": "Registro removido com sucesso"}
