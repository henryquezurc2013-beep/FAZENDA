from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional, List
from datetime import date

from database import supabase, get_fazenda_id

router = APIRouter()

# Supabase animais columns:
# id, fazenda_id, brinco, nome, tipo, raca, sexo, data_nascimento, data_compra,
# origem, valor_compra, pasto_atual, peso_atual, status, data_morte, motivo_morte,
# custo_kg, custo_arroba, obs, criado_em

_ALLOWED_FIELDS = {
    "brinco", "nome", "tipo", "raca", "sexo", "data_nascimento", "data_compra",
    "origem", "valor_compra", "pasto_atual", "peso_atual", "status", "data_morte",
    "motivo_morte", "custo_kg", "custo_arroba", "obs", "fazenda_id",
}


def _calc_idade(data_nascimento: str):
    try:
        nasc = date.fromisoformat(data_nascimento)
        hoje = date.today()
        anos = hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
        meses_total = (hoje.year - nasc.year) * 12 + (hoje.month - nasc.month)
        if hoje.day < nasc.day:
            meses_total -= 1
        return anos, meses_total % 12
    except Exception:
        return 0, 0


def _to_out(animal: dict) -> dict:
    d = dict(animal)
    anos, meses = _calc_idade(animal.get("data_nascimento") or "")
    d["idade_anos"] = anos
    d["idade_meses"] = meses
    # Backward compat: expose pasto_atual as pasto
    d["pasto"] = animal.get("pasto_atual")
    return d


def _calcular_custos(data: dict) -> dict:
    vc = data.get("valor_compra")
    pa = data.get("peso_atual")
    if vc and vc > 0 and pa and pa > 0:
        data["custo_kg"] = round(vc / pa, 2)
        data["custo_arroba"] = round(vc / (pa / 15), 2)
    else:
        data["custo_kg"] = None
        data["custo_arroba"] = None
    return data


def _clean(data: dict) -> dict:
    """Keep only fields that exist in Supabase animais table."""
    # Map old field names to new
    if "pasto" in data and "pasto_atual" not in data:
        data["pasto_atual"] = data.pop("pasto")
    elif "pasto" in data:
        data.pop("pasto")
    # Remove fields not in Supabase
    return {k: v for k, v in data.items() if k in _ALLOWED_FIELDS}


def _validate_and_fill(data: dict):
    required = ["brinco", "sexo", "tipo", "raca", "origem", "data_nascimento", "status"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")
    if data.get("status") == "MORTO":
        if not data.get("data_morte"):
            raise HTTPException(status_code=400, detail="data_morte é obrigatória quando status = MORTO")
        if not data.get("motivo_morte"):
            raise HTTPException(status_code=400, detail="motivo_morte é obrigatório quando status = MORTO")
    return data


@router.get("")
def listar_animais(
    request: Request,
    brinco: Optional[str] = Query(None),
    pasto: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sexo: Optional[str] = Query(None),
    raca: Optional[str] = Query(None),
    lote: Optional[str] = Query(None),
    sem_lote: Optional[str] = Query(None),
):
    fid = get_fazenda_id(request)
    q = supabase.table("animais").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    if brinco:
        q = q.ilike("brinco", brinco)
    if pasto:
        q = q.ilike("pasto_atual", pasto)
    if tipo:
        q = q.ilike("tipo", tipo)
    if status:
        q = q.ilike("status", status)
    if sexo:
        q = q.ilike("sexo", sexo)
    if raca:
        q = q.ilike("raca", raca)
    rows = q.limit(500).execute().data

    if lote or sem_lote == "1":
        # lote_animais lookup
        la_q = supabase.table("lote_animais").select("brinco,lote_id")
        if fid > 0:
            la_q = la_q.eq("fazenda_id", fid)
        la_rows = la_q.is_("data_saida", "null").execute().data
        brinco_lote = {r["brinco"]: r["lote_id"] for r in la_rows}
        if sem_lote == "1":
            rows = [r for r in rows if r.get("brinco") not in brinco_lote]
        if lote:
            lote_ids = [r["id"] for r in supabase.table("lotes").select("id,nome").ilike("nome", f"%{lote}%").execute().data]
            rows = [r for r in rows if brinco_lote.get(r.get("brinco")) in lote_ids]

    return [_to_out(a) for a in rows]


@router.get("/{brinco}")
def buscar_animal(brinco: str):
    rows = supabase.table("animais").select("*").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    return _to_out(rows[0])


@router.post("", status_code=201)
def criar_animal(request: Request, body: dict):
    existing = supabase.table("animais").select("id").ilike("brinco", body.get("brinco", "")).limit(1).execute().data
    if existing:
        raise HTTPException(status_code=400, detail="Brinco já cadastrado")
    data = _clean(dict(body))
    _validate_and_fill(data)
    fid = get_fazenda_id(request)
    if fid > 0:
        data["fazenda_id"] = fid
    _calcular_custos(data)
    result = supabase.table("animais").insert(data).execute().data[0]
    return _to_out(result)


@router.put("/{brinco}")
def atualizar_animal(brinco: str, body: dict):
    rows = supabase.table("animais").select("*").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    animal = rows[0]
    update_data = _clean({k: v for k, v in body.items() if k != "brinco"})
    merged = dict(animal)
    merged.update(update_data)
    _validate_and_fill(merged)
    _calcular_custos(merged)
    update_clean = _clean(update_data)
    supabase.table("animais").update(update_clean).eq("id", animal["id"]).execute()
    result = supabase.table("animais").select("*").eq("id", animal["id"]).limit(1).execute().data[0]
    return _to_out(result)


@router.delete("/{brinco}")
def deletar_animal(brinco: str):
    rows = supabase.table("animais").select("id").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    supabase.table("animais").delete().eq("id", rows[0]["id"]).execute()
    return {"mensagem": "Animal removido com sucesso"}


@router.get("/{brinco}/pesagens")
def pesagens_do_animal(brinco: str):
    rows = supabase.table("animais").select("id").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    data = supabase.table("pesagens").select("*").ilike("brinco", brinco).order("data", desc=True).execute().data
    return [{**r, "data_pesagem": r.get("data"), "peso": r.get("peso_kg")} for r in data]


@router.get("/{brinco}/sanidade")
def sanidade_do_animal(brinco: str):
    rows = supabase.table("animais").select("id").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    return supabase.table("sanidade").select("*").ilike("brinco", brinco).order("data", desc=True).execute().data
