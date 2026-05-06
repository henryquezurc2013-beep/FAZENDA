from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
from datetime import date

from database import supabase, get_fazenda_id

router = APIRouter()


@router.get("")
def listar_pesagens(
    request: Request,
    brinco: Optional[str] = Query(None),
    mes: Optional[int] = Query(None),
    ano: Optional[int] = Query(None),
):
    fid = get_fazenda_id(request)
    q = supabase.table("pesagens").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    if brinco:
        q = q.ilike("brinco", brinco)
    if ano:
        q = q.like("data", f"{ano}-%")
    if mes and ano:
        q = q.like("data", f"{ano}-{mes:02d}-%")
    rows = q.order("data", desc=True).execute().data
    # Normalize output to keep backward compat with frontend
    return [_normalize(r) for r in rows]


def _normalize(r: dict) -> dict:
    """Map Supabase column names to the names the frontend expects."""
    return {
        **r,
        "data_pesagem": r.get("data"),
        "peso": r.get("peso_kg"),
        "media_dia_kg": r.get("gmd"),
    }


@router.post("", status_code=201)
def criar_pesagem(request: Request, body: dict):
    fid = get_fazenda_id(request)
    brinco = body.get("brinco")
    # Accept both old (data_pesagem/peso) and new (data/peso_kg) field names
    data_str = body.get("data") or body.get("data_pesagem")
    peso = body.get("peso_kg") or body.get("peso")
    pasto = body.get("pasto")

    if not brinco or not data_str or peso is None:
        raise HTTPException(status_code=400, detail="brinco, data e peso_kg são obrigatórios.")

    animal_rows = supabase.table("animais").select("*").ilike("brinco", brinco).limit(1).execute().data
    if not animal_rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    animal = animal_rows[0]

    try:
        dt_atual = date.fromisoformat(data_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="data inválida, use YYYY-MM-DD")

    ant_rows = supabase.table("pesagens").select("*").ilike("brinco", brinco).lt("data", data_str).order("data", desc=True).limit(1).execute().data
    anterior = ant_rows[0] if ant_rows else None

    ganho_kg = gmd = 0.0
    dias_periodo = 0
    if anterior:
        ganho_kg = round(peso - (anterior.get("peso_kg") or 0), 2)
        try:
            dias_periodo = (dt_atual - date.fromisoformat(anterior["data"])).days
            if dias_periodo > 0:
                gmd = round(ganho_kg / dias_periodo, 3)
        except Exception:
            pass

    fid_final = fid if fid > 0 else (animal.get("fazenda_id") or 1)
    row = supabase.table("pesagens").insert({
        "brinco": brinco,
        "data": data_str,
        "peso_kg": peso,
        "ganho_kg": ganho_kg,
        "gmd": gmd,
        "dias_periodo": dias_periodo,
        "pasto": pasto or animal.get("pasto_atual"),
        "fazenda_id": fid_final,
    }).execute().data[0]

    update = {"peso_atual": peso}
    vc = animal.get("valor_compra")
    if vc and vc > 0 and peso > 0:
        update["custo_kg"] = round(vc / peso, 2)
        update["custo_arroba"] = round(vc / (peso / 15), 2)
    supabase.table("animais").update(update).eq("id", animal["id"]).execute()

    return _normalize(row)


@router.put("/{id}")
def atualizar_pesagem(id: int, body: dict):
    rows = supabase.table("pesagens").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Pesagem não encontrada")
    update_data = {}
    if "data" in body or "data_pesagem" in body:
        update_data["data"] = body.get("data") or body.get("data_pesagem")
    if "peso_kg" in body or "peso" in body:
        update_data["peso_kg"] = body.get("peso_kg") or body.get("peso")
    if "pasto" in body:
        update_data["pasto"] = body["pasto"]
    if "obs" in body:
        update_data["obs"] = body["obs"]
    if update_data:
        supabase.table("pesagens").update(update_data).eq("id", id).execute()
    result = supabase.table("pesagens").select("*").eq("id", id).limit(1).execute().data[0]
    return _normalize(result)


@router.delete("/{id}")
def deletar_pesagem(id: int):
    rows = supabase.table("pesagens").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Pesagem não encontrada")
    supabase.table("pesagens").delete().eq("id", id).execute()
    return {"mensagem": "Pesagem removida com sucesso"}
