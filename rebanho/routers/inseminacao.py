import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from database import supabase, get_fazenda_id

router = APIRouter()

# Supabase inseminacoes columns:
# id, fazenda_id, brinco_femea, data, tipo, touro_brinco, semen_partida,
# tecnico, resultado, data_resultado, data_parto_prev, obs, criado_em

_ALLOWED_FIELDS = {
    "brinco_femea", "data", "tipo", "touro_brinco", "semen_partida",
    "tecnico", "resultado", "data_resultado", "data_parto_prev", "obs", "fazenda_id",
}


def _clean(data: dict) -> dict:
    """Map old field names to Supabase column names."""
    out = {}
    for k, v in data.items():
        if k == "brinco":
            out["brinco_femea"] = v
        elif k == "data_insem":
            out["data"] = v
        elif k == "prenhez":
            out["resultado"] = v
        elif k == "data_nasc_cria":
            out["data_resultado"] = v
        elif k in _ALLOWED_FIELDS:
            out[k] = v
        # Discard: status, qtd_crias (not in Supabase schema)
    return out


def _normalize(r: dict) -> dict:
    """Add backward-compat aliases for frontend."""
    return {
        **r,
        "brinco": r.get("brinco_femea"),
        "data_insem": r.get("data"),
        "prenhez": r.get("resultado"),
        "data_nasc_cria": r.get("data_resultado"),
        "status": r.get("resultado") or "AGUARDANDO",
    }


def _fmt_data(valor: Optional[str]) -> str:
    if not valor:
        return ""
    try:
        return date.fromisoformat(valor).strftime("%d/%m/%Y")
    except ValueError:
        return valor


@router.get("/exportar")
def exportar_inseminacoes(
    brinco: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    q = supabase.table("inseminacoes").select("*")
    if brinco:
        q = q.ilike("brinco_femea", brinco)
    if status:
        q = q.ilike("resultado", status)
    if data_inicio:
        q = q.gte("data", data_inicio)
    if data_fim:
        q = q.lte("data", data_fim)
    registros = q.order("data", desc=True).execute().data

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["Brinco Fêmea", "Data Inseminação", "Tipo", "Touro", "Técnico",
                     "Resultado", "Data Resultado", "Previsão Parto", "Observação"])
    for r in registros:
        writer.writerow([
            r.get("brinco_femea"), _fmt_data(r.get("data")), r.get("tipo") or "",
            r.get("touro_brinco") or "", r.get("tecnico") or "",
            r.get("resultado") or "", _fmt_data(r.get("data_resultado")),
            _fmt_data(r.get("data_parto_prev")), r.get("obs") or "",
        ])
    output.seek(0)
    nome_arquivo = f"inseminacoes_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


@router.get("")
def listar_inseminacoes(
    request: Request,
    brinco: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    fid = get_fazenda_id(request)
    q = supabase.table("inseminacoes").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    if brinco:
        q = q.ilike("brinco_femea", brinco)
    if status:
        q = q.ilike("resultado", status)
    if data_inicio:
        q = q.gte("data", data_inicio)
    if data_fim:
        q = q.lte("data", data_fim)
    rows = q.order("data", desc=True).execute().data
    return [_normalize(r) for r in rows]


@router.post("", status_code=201)
def criar_inseminacao(request: Request, body: dict):
    fid = get_fazenda_id(request)
    brinco = body.get("brinco_femea") or body.get("brinco")
    animal_rows = supabase.table("animais").select("*").ilike("brinco", brinco).limit(1).execute().data
    if not animal_rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    animal = animal_rows[0]
    if animal.get("sexo") and animal["sexo"].upper() == "MACHO":
        raise HTTPException(status_code=400, detail="Inseminação só pode ser registrada para fêmeas")
    data_val = body.get("data") or body.get("data_insem")
    if not data_val:
        raise HTTPException(status_code=400, detail="Campo obrigatório: data")
    data = _clean(dict(body))
    data["brinco_femea"] = brinco
    data["fazenda_id"] = fid if fid > 0 else (animal.get("fazenda_id") or 1)
    result = supabase.table("inseminacoes").insert(data).execute().data[0]
    return _normalize(result)


@router.put("/{id}")
def atualizar_inseminacao(id: int, body: dict):
    rows = supabase.table("inseminacoes").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Inseminação não encontrada")
    update_data = _clean({k: v for k, v in body.items() if k not in ("brinco", "brinco_femea")})
    supabase.table("inseminacoes").update(update_data).eq("id", id).execute()
    result = supabase.table("inseminacoes").select("*").eq("id", id).limit(1).execute().data[0]
    return _normalize(result)


@router.delete("/{id}")
def deletar_inseminacao(id: int):
    rows = supabase.table("inseminacoes").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Inseminação não encontrada")
    supabase.table("inseminacoes").delete().eq("id", id).execute()
    return {"mensagem": "Inseminação removida com sucesso"}
