from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from database import supabase
from schemas import CompraCreate, VendaCreate, DespesaCreate

router_compras = APIRouter()
router_vendas = APIRouter()
router_despesas = APIRouter()


def _parse_data(valor: str, campo: str) -> date:
    try:
        return date.fromisoformat(valor)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"{campo} inválida, use YYYY-MM-DD")


# ─── COMPRAS ─────────────────────────────────────────────────────────────────

@router_compras.get("")
def listar_compras(
    fornecedor: Optional[str] = Query(None),
    mes: Optional[int] = Query(None),
    ano: Optional[int] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    q = supabase.table("compras").select("*")
    if fornecedor:
        q = q.ilike("fornecedor", f"%{fornecedor}%")
    if mes:
        q = q.eq("mes", mes)
    if ano:
        q = q.eq("ano", ano)
    if data_inicio:
        q = q.gte("data", data_inicio)
    if data_fim:
        q = q.lte("data", data_fim)
    return q.order("data", desc=True).execute().data


@router_compras.post("", status_code=201)
def criar_compra(payload: CompraCreate):
    missing = [f for f in ("fornecedor", "data", "valor_unit", "quantidade") if not getattr(payload, f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")
    dt = _parse_data(payload.data, "data")
    data = payload.model_dump()
    data["valor_total"] = round((payload.valor_unit or 0) * (payload.quantidade or 1), 2)
    data["mes"] = dt.month
    data["ano"] = dt.year
    return supabase.table("compras").insert(data).execute().data[0]


@router_compras.put("/{id}")
def atualizar_compra(id: int, payload: CompraCreate):
    rows = supabase.table("compras").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Compra não encontrada")
    data = {**rows[0], **payload.model_dump(exclude_unset=True)}
    data["valor_total"] = round((data.get("valor_unit") or 0) * (data.get("quantidade") or 1), 2)
    if data.get("data"):
        dt = _parse_data(data["data"], "data")
        data["mes"] = dt.month
        data["ano"] = dt.year
    supabase.table("compras").update(data).eq("id", id).execute()
    return supabase.table("compras").select("*").eq("id", id).limit(1).execute().data[0]


@router_compras.delete("/{id}")
def deletar_compra(id: int):
    rows = supabase.table("compras").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Compra não encontrada")
    supabase.table("compras").delete().eq("id", id).execute()
    return {"mensagem": "Compra removida com sucesso"}


# ─── VENDAS ──────────────────────────────────────────────────────────────────

@router_vendas.get("")
def listar_vendas(
    cliente: Optional[str] = Query(None),
    mes: Optional[int] = Query(None),
    ano: Optional[int] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    q = supabase.table("vendas").select("*")
    if cliente:
        q = q.ilike("cliente", f"%{cliente}%")
    if mes:
        q = q.eq("mes", mes)
    if ano:
        q = q.eq("ano", ano)
    if data_inicio:
        q = q.gte("data", data_inicio)
    if data_fim:
        q = q.lte("data", data_fim)
    return q.order("data", desc=True).execute().data


@router_vendas.post("", status_code=201)
def criar_venda(payload: VendaCreate):
    missing = [f for f in ("cliente", "data", "valor_unit", "quantidade") if not getattr(payload, f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")
    dt = _parse_data(payload.data, "data")
    data = payload.model_dump()
    data["valor_total"] = round((payload.valor_unit or 0) * (payload.quantidade or 1), 2)
    data["mes"] = dt.month
    data["ano"] = dt.year
    return supabase.table("vendas").insert(data).execute().data[0]


@router_vendas.put("/{id}")
def atualizar_venda(id: int, payload: VendaCreate):
    rows = supabase.table("vendas").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Venda não encontrada")
    data = {**rows[0], **payload.model_dump(exclude_unset=True)}
    data["valor_total"] = round((data.get("valor_unit") or 0) * (data.get("quantidade") or 1), 2)
    if data.get("data"):
        dt = _parse_data(data["data"], "data")
        data["mes"] = dt.month
        data["ano"] = dt.year
    supabase.table("vendas").update(data).eq("id", id).execute()
    return supabase.table("vendas").select("*").eq("id", id).limit(1).execute().data[0]


@router_vendas.delete("/{id}")
def deletar_venda(id: int):
    rows = supabase.table("vendas").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Venda não encontrada")
    supabase.table("vendas").delete().eq("id", id).execute()
    return {"mensagem": "Venda removida com sucesso"}


# ─── DESPESAS ────────────────────────────────────────────────────────────────

def _despesa_out(d: dict) -> dict:
    hoje = date.today().isoformat()
    row = dict(d)
    row["vencida"] = bool(
        d.get("vencimento") and d["vencimento"] < hoje and (d.get("status") or "").upper() == "PENDENTE"
    )
    return row


@router_despesas.get("")
def listar_despesas(
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    mes: Optional[int] = Query(None),
    ano: Optional[int] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    q = supabase.table("despesas").select("*")
    if tipo:
        q = q.ilike("tipo", tipo)
    if status:
        q = q.ilike("status", status)
    if mes:
        q = q.eq("mes", mes)
    if ano:
        q = q.eq("ano", ano)
    if data_inicio:
        q = q.gte("vencimento", data_inicio)
    if data_fim:
        q = q.lte("vencimento", data_fim)
    rows = q.order("vencimento", desc=True).execute().data
    return [_despesa_out(d) for d in rows]


@router_despesas.post("", status_code=201)
def criar_despesa(payload: DespesaCreate):
    missing = [f for f in ("valor", "vencimento") if not getattr(payload, f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")
    dt = _parse_data(payload.vencimento, "vencimento")
    data = payload.model_dump()
    if not data.get("status"):
        data["status"] = "PENDENTE"
    data["mes"] = dt.month
    data["ano"] = dt.year
    row = supabase.table("despesas").insert(data).execute().data[0]
    return _despesa_out(row)


@router_despesas.put("/{id}")
def atualizar_despesa(id: int, payload: DespesaCreate):
    rows = supabase.table("despesas").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    data = {**rows[0], **payload.model_dump(exclude_unset=True)}
    if data.get("vencimento"):
        dt = _parse_data(data["vencimento"], "vencimento")
        data["mes"] = dt.month
        data["ano"] = dt.year
    supabase.table("despesas").update(data).eq("id", id).execute()
    row = supabase.table("despesas").select("*").eq("id", id).limit(1).execute().data[0]
    return _despesa_out(row)


@router_despesas.delete("/{id}")
def deletar_despesa(id: int):
    rows = supabase.table("despesas").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    supabase.table("despesas").delete().eq("id", id).execute()
    return {"mensagem": "Despesa removida com sucesso"}
