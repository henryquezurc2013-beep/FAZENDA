from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import supabase

router = APIRouter()


class FazendaIn(BaseModel):
    nome: str
    apelido: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    area_ha: Optional[float] = None
    cor: Optional[str] = '#1B5E20'


def _kpis(f: dict) -> dict:
    fid = f["id"]
    animais = supabase.table("animais").select("id,status").eq("fazenda_id", fid).execute().data
    total_animais = len(animais)
    total_ativos = sum(1 for a in animais if (a.get("status") or "").upper() == "ATIVO")
    piquetes = supabase.table("piquetes").select("id").eq("fazenda_id", fid).execute().data
    total_piquetes = len(piquetes)
    return {
        "id": f["id"], "nome": f["nome"], "apelido": f.get("apelido"),
        "cidade": f.get("cidade"), "uf": f.get("uf"), "area_ha": f.get("area_ha"),
        "cor": f.get("cor"), "ativo": f.get("ativo"),
        "total_animais": total_animais, "total_ativos": total_ativos,
        "total_piquetes": total_piquetes, "ua_ha_media": None,
    }


@router.get("")
def listar_fazendas():
    fazendas = supabase.table("fazendas").select("*").eq("ativo", True).order("id").execute().data
    return [_kpis(f) for f in fazendas]


@router.post("")
def criar_fazenda(body: FazendaIn):
    existing = supabase.table("fazendas").select("id").eq("nome", body.nome).limit(1).execute().data
    if existing:
        raise HTTPException(400, "Já existe uma fazenda com esse nome")
    data = body.model_dump()
    data["ativo"] = True
    result = supabase.table("fazendas").insert(data).execute().data[0]
    return {"id": result["id"], "ok": True}


@router.put("/{fid}")
def editar_fazenda(fid: int, body: FazendaIn):
    rows = supabase.table("fazendas").select("id").eq("id", fid).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Fazenda não encontrada")
    supabase.table("fazendas").update(body.model_dump()).eq("id", fid).execute()
    return {"ok": True}


@router.delete("/{fid}")
def excluir_fazenda(fid: int):
    rows = supabase.table("fazendas").select("id").eq("id", fid).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Fazenda não encontrada")
    tem_animais = supabase.table("animais").select("id").eq("fazenda_id", fid).limit(1).execute().data
    tem_piquetes = supabase.table("piquetes").select("id").eq("fazenda_id", fid).limit(1).execute().data
    if tem_animais or tem_piquetes:
        raise HTTPException(400, "Fazenda possui animais ou piquetes vinculados. Remova-os primeiro.")
    supabase.table("fazendas").delete().eq("id", fid).execute()
    return {"ok": True}


@router.get("/{fid}/resumo")
def resumo_fazenda(fid: int):
    rows = supabase.table("fazendas").select("*").eq("id", fid).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Fazenda não encontrada")
    f = rows[0]
    hoje = date.today()
    mes_str = hoje.strftime("%Y-%m")

    ativos = supabase.table("animais").select("id").eq("fazenda_id", fid).eq("status", "ATIVO").execute().data
    total_ativos = len(ativos)

    vendas = supabase.table("vendas").select("valor_total").ilike("data", f"{mes_str}%").execute().data
    receita = sum(v["valor_total"] or 0 for v in vendas)
    despesas_rows = supabase.table("despesas").select("valor").ilike("vencimento", f"{mes_str}%").eq("status", "PENDENTE").execute().data
    despesa = sum(d["valor"] or 0 for d in despesas_rows)

    ultima_pes_rows = supabase.table("pesagens").select("data").eq("fazenda_id", fid).order("data", desc=True).limit(1).execute().data
    ultima_pes = ultima_pes_rows[0] if ultima_pes_rows else None

    piquetes = supabase.table("piquetes").select("id,status").eq("fazenda_id", fid).execute().data
    from routers.pastagem import semaforo_piquete
    verde = sum(1 for p in piquetes if semaforo_piquete(p["id"], None)["semaforo"] == "VERDE")
    ocupado = sum(1 for p in piquetes if semaforo_piquete(p["id"], None)["semaforo"] == "OCUPADO")

    lotes_conf = supabase.table("lotes_confinamento").select("*").eq("fazenda_id", fid).eq("status", "ATIVO").execute().data
    animais_conf = sum(l["qtd_animais"] for l in lotes_conf)
    gmds_conf = []
    for lc in lotes_conf:
        try:
            ult = supabase.table("pesagem_confinamento").select("peso_medio_kg").eq("lote_conf_id", lc["id"]).order("data", desc=True).limit(1).execute().data
            peso_at = ult[0]["peso_medio_kg"] if ult else lc["peso_medio_entrada"]
            dias_lc = max((hoje - date.fromisoformat(lc["data_entrada"])).days, 1)
            gmd_lc = (peso_at - lc["peso_medio_entrada"]) / dias_lc
            if gmd_lc > 0:
                gmds_conf.append(gmd_lc)
        except Exception:
            pass

    return {
        "fazenda": {"id": f["id"], "nome": f["nome"], "cor": f.get("cor"), "apelido": f.get("apelido"),
                    "cidade": f.get("cidade"), "uf": f.get("uf"), "area_ha": f.get("area_ha")},
        "rebanho": {"total_ativo": total_ativos},
        "pastagem": {"verde": verde, "ocupado": ocupado},
        "financeiro": {"receita_mes": round(float(receita), 2),
                       "despesa_mes": round(float(despesa), 2),
                       "saldo_mes": round(float(receita) - float(despesa), 2)},
        "ultima_pesagem": ultima_pes["data"] if ultima_pes else None,
        "confinamento": {
            "lotes_ativos": len(lotes_conf),
            "animais_confinados": animais_conf,
            "gmd_medio": round(sum(gmds_conf) / len(gmds_conf), 2) if gmds_conf else None,
        },
    }


def seed_fazendas(db=None):
    rows = supabase.table("fazendas").select("id").limit(1).execute().data
    if rows:
        return
    supabase.table("fazendas").insert([
        {"nome": "Fazenda Ipanema", "apelido": "IPM", "cidade": "Luziânia", "uf": "GO", "area_ha": 500, "cor": "#0d1f3c", "ativo": True},
        {"nome": "Fazenda São João", "apelido": "SJO", "cidade": "Cristalina", "uf": "GO", "area_ha": 300, "cor": "#14532d", "ativo": True},
    ]).execute()
