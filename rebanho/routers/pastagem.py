import json as _json
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response

from database import supabase, get_fazenda_id

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────

def calcular_ua(peso_medio_kg: float, qtd_animais: int) -> float:
    if not peso_medio_kg or not qtd_animais:
        return 0.0
    return round((peso_medio_kg / 450) * qtd_animais, 1)


def calcular_taxa_lotacao(ua_total: float, area_ha: float) -> float:
    if not area_ha or area_ha == 0:
        return 0.0
    return round(ua_total / area_ha, 2)


def _pq_coords(coordenadas):
    if not coordenadas:
        return None
    if isinstance(coordenadas, (list, dict)):
        return coordenadas
    try:
        return _json.loads(coordenadas)
    except Exception:
        return None


def semaforo_piquete(piquete_id: int, db=None) -> dict:
    rows = supabase.table("piquetes").select("*").eq("id", piquete_id).limit(1).execute().data
    if not rows:
        return {"semaforo": "SEM_DADOS", "altura_atual": None,
                "dias_descanso": 0, "dias_ocupacao": 0, "mensagem": "Piquete não encontrado"}
    piquete = rows[0]
    hoje = date.today()

    med_rows = supabase.table("medicao_pastagem").select("*").eq("piquete_id", piquete_id).order("data", desc=True).order("id", desc=True).limit(1).execute().data
    medicao = med_rows[0] if med_rows else None

    altura_atual = None
    dias_sem_medicao = 999
    if medicao:
        try:
            d_med = date.fromisoformat(medicao["data"])
            dias_sem_medicao = (hoje - d_med).days
            altura_atual = medicao["altura_cm"]
        except Exception:
            pass

    # Active lote: use lotes table (piquete_id + status ATIVO)
    lote_rows = supabase.table("lotes").select("*").eq("piquete_id", piquete_id).ilike("status", "ATIVO").order("data_entrada", desc=True).limit(1).execute().data
    lote_ativo = lote_rows[0] if lote_rows else None

    # Last exit: last lote with data_saida set
    last_out = supabase.table("lotes").select("data_saida").eq("piquete_id", piquete_id).not_.is_("data_saida", "null").order("data_saida", desc=True).limit(1).execute().data

    dias_descanso = 0
    if last_out and last_out[0].get("data_saida"):
        try:
            d_saida = date.fromisoformat(last_out[0]["data_saida"])
            dias_descanso = (hoje - d_saida).days
        except Exception:
            pass

    dias_ocupacao = 0
    if lote_ativo and lote_ativo.get("data_entrada"):
        try:
            d_ent = date.fromisoformat(lote_ativo["data_entrada"])
            dias_ocupacao = (hoje - d_ent).days
        except Exception:
            pass

    alt_entrada = piquete.get("altura_entrada_cm") or 35
    alt_saida   = piquete.get("altura_saida_cm") or 15
    desc_alvo   = piquete.get("descanso_alvo_dias") or 28

    if dias_sem_medicao > 14:
        return {
            "semaforo": "SEM_DADOS",
            "altura_atual": altura_atual,
            "dias_descanso": dias_descanso,
            "dias_ocupacao": dias_ocupacao,
            "lote": lote_ativo["nome"] if lote_ativo else None,
            "mensagem": f"Sem medição há {dias_sem_medicao} dias. Medir o capim.",
        }

    if lote_ativo:
        lote_nome = lote_ativo.get("nome") or str(lote_ativo.get("id", ""))
        if (altura_atual is not None and altura_atual <= alt_saida) or dias_ocupacao >= desc_alvo:
            motivo = (f"Altura: {altura_atual} cm (mínimo {alt_saida} cm)"
                      if altura_atual and altura_atual <= alt_saida
                      else f"Ocupação: {dias_ocupacao} dias (alvo {desc_alvo} dias)")
            return {
                "semaforo": "SAIR_AGORA",
                "altura_atual": altura_atual,
                "dias_descanso": dias_descanso,
                "dias_ocupacao": dias_ocupacao,
                "lote": lote_nome,
                "mensagem": f"Retirar o lote agora! {motivo}.",
            }
        return {
            "semaforo": "OCUPADO",
            "altura_atual": altura_atual,
            "dias_descanso": dias_descanso,
            "dias_ocupacao": dias_ocupacao,
            "lote": lote_nome,
            "mensagem": f"Ocupado por {lote_nome}. {dias_ocupacao} dias de ocupação.",
        }

    pasto_pronto = altura_atual is not None and altura_atual >= alt_entrada
    descanso_ok  = dias_descanso >= desc_alvo

    if pasto_pronto and descanso_ok:
        return {
            "semaforo": "VERDE",
            "altura_atual": altura_atual,
            "dias_descanso": dias_descanso,
            "dias_ocupacao": 0,
            "lote": None,
            "mensagem": f"Pronto para entrada. Altura: {altura_atual} cm. Descanso: {dias_descanso} dias.",
        }
    if not pasto_pronto and not descanso_ok:
        return {
            "semaforo": "VERMELHO",
            "altura_atual": altura_atual,
            "dias_descanso": dias_descanso,
            "dias_ocupacao": 0,
            "lote": None,
            "mensagem": f"Não entrar. Altura: {altura_atual} cm (alvo {alt_entrada} cm). Descanso: {dias_descanso}/{desc_alvo} dias.",
        }
    return {
        "semaforo": "AMARELO",
        "altura_atual": altura_atual,
        "dias_descanso": dias_descanso,
        "dias_ocupacao": 0,
        "lote": None,
        "mensagem": (
            f"Quase pronto. Altura: {altura_atual} cm. Descanso: {dias_descanso} dias."
            if not descanso_ok
            else f"Pasto pronto mas descanso insuficiente ({dias_descanso}/{desc_alvo} dias)."
        ),
    }


def _pasto_dict(p: dict) -> dict:
    qtd_rows = supabase.table("piquetes").select("id").eq("pasto_id", p["id"]).execute().data
    return {
        "id": p["id"], "nome": p["nome"], "area_ha": p.get("area_ha"),
        "tipo_capim": p.get("tipo_capim"), "sistema": p.get("sistema"),
        "status": p.get("status"), "obs": p.get("obs"), "qtd_piquetes": len(qtd_rows),
    }


def _piquete_dict(pq: dict, db=None, incluir_semaforo: bool = True) -> dict:
    d = {
        "id": pq["id"], "pasto_id": pq.get("pasto_id"), "nome": pq["nome"],
        "area_ha": pq.get("area_ha"), "tipo_capim": pq.get("tipo_capim"),
        "altura_entrada_cm": pq.get("altura_entrada_cm"),
        "altura_saida_cm": pq.get("altura_saida_cm"),
        "descanso_alvo_dias": pq.get("descanso_alvo_dias"),
        "tem_bebedouro": pq.get("tem_bebedouro"), "tem_cocho": pq.get("tem_cocho"),
        "tem_sombra": pq.get("tem_sombra"), "status": pq.get("status"), "obs": pq.get("obs"),
        "coordenadas": _pq_coords(pq.get("coordenadas")),
        "cor_mapa": pq.get("cor_mapa") or '#2E7D32',
        "icone_mapa": pq.get("icone_mapa") or '🌿',
    }
    if pq.get("pasto_id"):
        pasto_rows = supabase.table("pastos").select("nome").eq("id", pq["pasto_id"]).limit(1).execute().data
        d["pasto_nome"] = pasto_rows[0]["nome"] if pasto_rows else ""
    else:
        d["pasto_nome"] = ""
    if incluir_semaforo:
        d["semaforo"] = semaforo_piquete(pq["id"], None)
    return d


_COR_SEM = {
    "VERDE":     "#2E7D32",
    "AMARELO":   "#F9A825",
    "VERMELHO":  "#C62828",
    "SAIR_AGORA":"#B71C1C",
    "OCUPADO":   "#1565C0",
    "SEM_DADOS": "#757575",
}


def _piquete_mapa_dict(pq: dict) -> dict:
    sem = semaforo_piquete(pq["id"], None)
    pasto_nome = ""
    if pq.get("pasto_id"):
        pasto_rows = supabase.table("pastos").select("nome").eq("id", pq["pasto_id"]).limit(1).execute().data
        pasto_nome = pasto_rows[0]["nome"] if pasto_rows else ""

    lote_rows = supabase.table("lotes").select("*").eq("piquete_id", pq["id"]).ilike("status", "ATIVO").order("data_entrada", desc=True).limit(1).execute().data
    lote_a = lote_rows[0] if lote_rows else None

    med_rows = supabase.table("medicao_pastagem").select("data").eq("piquete_id", pq["id"]).order("data", desc=True).limit(1).execute().data
    med = med_rows[0] if med_rows else None

    ua_ha = None
    classificacao_ua = None
    if lote_a and pq.get("area_ha"):
        qtd = lote_a.get("qtd_animais") or 0
        ua = qtd * 380 / 450
        ua_ha = round(ua / pq["area_ha"], 2) if pq["area_ha"] else None
        if ua_ha:
            if   ua_ha < 1.0: classificacao_ua = "LEVE"
            elif ua_ha < 2.5: classificacao_ua = "IDEAL"
            elif ua_ha < 4.0: classificacao_ua = "ALTA"
            else:             classificacao_ua = "CRITICA"

    sem_str = sem.get("semaforo", "SEM_DADOS")
    return {
        "id": pq["id"],
        "nome": pq["nome"],
        "pasto": pasto_nome,
        "coordenadas": _pq_coords(pq.get("coordenadas")),
        "area_ha": pq.get("area_ha"),
        "tipo_capim": pq.get("tipo_capim"),
        "cor_mapa": pq.get("cor_mapa") or '#2E7D32',
        "semaforo": sem_str,
        "cor_semaforo": _COR_SEM.get(sem_str, "#757575"),
        "altura_atual": sem.get("altura_atual"),
        "dias_descanso": sem.get("dias_descanso", 0),
        "dias_ocupacao": sem.get("dias_ocupacao", 0),
        "lote_atual": lote_a["nome"] if lote_a else None,
        "qtd_animais": lote_a.get("qtd_animais") if lote_a else None,
        "ua_ha": ua_ha,
        "classificacao_ua": classificacao_ua,
        "ultima_medicao": med["data"] if med else None,
        "mensagem": sem.get("mensagem", ""),
    }


# ── PASTOS ───────────────────────────────────────────────────────────

@router.get("/pastos")
def listar_pastos(request: Request):
    fid = get_fazenda_id(request)
    q = supabase.table("pastos").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    pastos = q.order("nome").execute().data
    return [_pasto_dict(p) for p in pastos]


@router.post("/pastos")
def criar_pasto(request: Request, body: dict):
    fid = get_fazenda_id(request)
    if not body.get("nome"):
        raise HTTPException(status_code=400, detail="Nome é obrigatório.")
    existente = supabase.table("pastos").select("id").ilike("nome", body["nome"]).limit(1).execute().data
    if existente:
        raise HTTPException(status_code=400, detail="Já existe um pasto com este nome.")
    data = {
        "nome": body["nome"], "area_ha": body.get("area_ha"),
        "tipo_capim": body.get("tipo_capim"), "sistema": body.get("sistema"),
        "status": body.get("status", "ATIVO"), "obs": body.get("obs"),
        "fazenda_id": fid if fid > 0 else 1,
    }
    result = supabase.table("pastos").insert(data).execute().data[0]
    return _pasto_dict(result)


@router.put("/pastos/{id}")
def editar_pasto(id: int, body: dict):
    rows = supabase.table("pastos").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Pasto não encontrado.")
    update = {k: body[k] for k in ["nome", "area_ha", "tipo_capim", "sistema", "status", "obs"] if k in body}
    supabase.table("pastos").update(update).eq("id", id).execute()
    updated = supabase.table("pastos").select("*").eq("id", id).limit(1).execute().data[0]
    return _pasto_dict(updated)


@router.delete("/pastos/{id}")
def excluir_pasto(id: int):
    rows = supabase.table("pastos").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Pasto não encontrado.")
    piquetes = supabase.table("piquetes").select("id").eq("pasto_id", id).limit(1).execute().data
    if piquetes:
        raise HTTPException(status_code=400, detail="Não é possível excluir pasto com piquetes cadastrados.")
    supabase.table("pastos").delete().eq("id", id).execute()
    return {"ok": True}


# ── PIQUETES ─────────────────────────────────────────────────────────

@router.get("/piquetes")
def listar_piquetes(
    request: Request,
    pasto_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
):
    fid = get_fazenda_id(request)
    q = supabase.table("piquetes").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    if pasto_id:
        q = q.eq("pasto_id", pasto_id)
    if status:
        q = q.ilike("status", status)
    piquetes = q.order("nome").execute().data
    return [_piquete_dict(pq) for pq in piquetes]


@router.post("/piquetes")
def criar_piquete(request: Request, body: dict):
    fid = get_fazenda_id(request)
    if not body.get("nome"):
        raise HTTPException(status_code=400, detail="Nome é obrigatório.")
    data = {
        "pasto_id": body.get("pasto_id"), "nome": body["nome"],
        "area_ha": body.get("area_ha"), "tipo_capim": body.get("tipo_capim"),
        "altura_entrada_cm": body.get("altura_entrada_cm"),
        "altura_saida_cm": body.get("altura_saida_cm"),
        "descanso_alvo_dias": body.get("descanso_alvo_dias"),
        "tem_bebedouro": body.get("tem_bebedouro", False),
        "tem_cocho": body.get("tem_cocho", False),
        "tem_sombra": body.get("tem_sombra", False),
        "status": body.get("status", "DISPONIVEL"), "obs": body.get("obs"),
        "fazenda_id": fid if fid > 0 else 1,
    }
    result = supabase.table("piquetes").insert(data).execute().data[0]
    return _piquete_dict(result)


@router.put("/piquetes/{id}")
def editar_piquete(id: int, body: dict):
    rows = supabase.table("piquetes").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")
    campos = ["pasto_id", "nome", "area_ha", "tipo_capim", "altura_entrada_cm",
              "altura_saida_cm", "descanso_alvo_dias", "tem_bebedouro",
              "tem_cocho", "tem_sombra", "status", "obs"]
    update = {k: body[k] for k in campos if k in body}
    supabase.table("piquetes").update(update).eq("id", id).execute()
    updated = supabase.table("piquetes").select("*").eq("id", id).limit(1).execute().data[0]
    return _piquete_dict(updated)


@router.delete("/piquetes/{id}")
def excluir_piquete(id: int):
    rows = supabase.table("piquetes").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")
    hist = supabase.table("manejo_pastagem").select("id").eq("piquete_id", id).limit(1).execute().data
    if hist:
        raise HTTPException(status_code=400, detail="Piquete tem histórico de manejo e não pode ser excluído.")
    supabase.table("piquetes").delete().eq("id", id).execute()
    return {"ok": True}


@router.get("/piquetes/{id}/semaforo")
def semaforo_endpoint(id: int):
    rows = supabase.table("piquetes").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")
    return semaforo_piquete(id, None)


@router.put("/piquetes/{id}/coordenadas")
def salvar_coordenadas(id: int, body: dict):
    rows = supabase.table("piquetes").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")
    coords = body.get("coordenadas")
    supabase.table("piquetes").update({"coordenadas": coords}).eq("id", id).execute()
    return {"ok": True, "id": id}


# ── MAPA ─────────────────────────────────────────────────────────────

@router.get("/mapa")
def mapa_dados():
    piquetes = supabase.table("piquetes").select("*").order("nome").execute().data
    piquetes_data = [_piquete_mapa_dict(pq) for pq in piquetes]

    todas_coords = [c for pd in piquetes_data if pd["coordenadas"] for c in pd["coordenadas"]]
    if todas_coords:
        lat_c = round(sum(c[0] for c in todas_coords) / len(todas_coords), 6)
        lng_c = round(sum(c[1] for c in todas_coords) / len(todas_coords), 6)
    else:
        lat_c, lng_c = -15.71, -47.92

    ini_mes = date.today().replace(day=1).isoformat()
    chuva_rows = supabase.table("chuva").select("mm").gte("data", ini_mes).execute().data
    mm_mes = sum(c["mm"] or 0 for c in chuva_rows)

    manejo_rows = []  # ganho_ha_kg not in Supabase manejo_pastagem schema
    ganhos_por_piquete = defaultdict(list)
    for m in manejo_rows:
        if m.get("ganho_ha_kg"):
            ganhos_por_piquete[m["piquete_id"]].append(m["ganho_ha_kg"])

    melhor_piquete = None
    if ganhos_por_piquete:
        best_pid = max(ganhos_por_piquete, key=lambda pid: sum(ganhos_por_piquete[pid]) / len(ganhos_por_piquete[pid]))
        best_avg = sum(ganhos_por_piquete[best_pid]) / len(ganhos_por_piquete[best_pid])
        pq_rows = supabase.table("piquetes").select("nome").eq("id", best_pid).limit(1).execute().data
        if pq_rows:
            melhor_piquete = {"nome": pq_rows[0]["nome"], "ganho_ha": round(best_avg, 1)}

    lotes_ativos_pasto = supabase.table("lotes").select("ua_ha,piquete_id").ilike("status", "ATIVO").not_.is_("piquete_id", "null").execute().data
    ua_total = sum((lt.get("ua_ha") or 0) * 1 for lt in lotes_ativos_pasto)  # approximate
    area_tot = sum(pq.get("area_ha") or 0 for pq in piquetes)
    ua_ha_media = round(ua_total / area_tot, 2) if area_tot > 0 else None

    proximo = None
    for pd in piquetes_data:
        if pd["semaforo"] == "AMARELO":
            dias = pd.get("dias_descanso") or 0
            if proximo is None or dias > proximo["dias_descanso"]:
                proximo = {"nome": pd["nome"], "dias_descanso": dias}

    return {
        "centro": {"lat": lat_c, "lng": lng_c},
        "zoom_inicial": 15,
        "piquetes": piquetes_data,
        "metricas": {
            "ua_ha_media": ua_ha_media,
            "chuva_mes_mm": round(float(mm_mes), 1),
            "melhor_piquete": melhor_piquete,
            "proximo_pronto": proximo,
        },
    }


@router.get("/mapa/exportar")
def exportar_geojson():
    piquetes = supabase.table("piquetes").select("*").order("nome").execute().data
    features = []
    for pq in piquetes:
        coords = _pq_coords(pq.get("coordenadas"))
        if not coords:
            continue
        geo_ring = [[c[1], c[0]] for c in coords]
        geo_ring.append(geo_ring[0])
        sem = semaforo_piquete(pq["id"], None)
        features.append({
            "type": "Feature",
            "properties": {
                "id": pq["id"], "nome": pq["nome"],
                "semaforo": sem.get("semaforo", "SEM_DADOS"),
                "area_ha": pq.get("area_ha"), "tipo_capim": pq.get("tipo_capim"),
            },
            "geometry": {"type": "Polygon", "coordinates": [geo_ring]},
        })
    geojson = _json.dumps(
        {"type": "FeatureCollection", "features": features},
        ensure_ascii=False, indent=2,
    )
    return Response(
        content=geojson,
        media_type="application/geo+json",
        headers={"Content-Disposition": "attachment; filename=fazenda-piquetes.geojson"},
    )


# ── MEDIÇÕES ─────────────────────────────────────────────────────────

@router.get("/medicoes")
def listar_medicoes(
    piquete_id: Optional[int] = Query(None),
    data_ini: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    q = supabase.table("medicao_pastagem").select("*")
    if piquete_id:
        q = q.eq("piquete_id", piquete_id)
    if data_ini:
        q = q.gte("data", data_ini)
    if data_fim:
        q = q.lte("data", data_fim)
    rows = q.order("data", desc=True).execute().data

    result = []
    pq_cache = {}
    for m in rows:
        pid = m["piquete_id"]
        if pid not in pq_cache:
            pq_rows = supabase.table("piquetes").select("nome").eq("id", pid).limit(1).execute().data
            pq_cache[pid] = pq_rows[0]["nome"] if pq_rows else ""
        result.append({
            "id": m["id"], "data": m["data"], "piquete_id": pid,
            "piquete_nome": pq_cache[pid],
            "altura_cm": m.get("altura_cm"), "massa_estimada": m.get("massa_estimada"),
            "cobertura_pct": m.get("cobertura_pct"), "falhas_pct": m.get("falhas_pct"),
            "planta_invasora": m.get("planta_invasora"), "condicao": m.get("condicao"),
            "responsavel": m.get("responsavel"), "obs": m.get("obs"),
        })
    return result


@router.post("/medicoes")
def criar_medicao(body: dict):
    if not body.get("piquete_id") or body.get("altura_cm") is None:
        raise HTTPException(status_code=400, detail="piquete_id e altura_cm são obrigatórios.")
    data = {
        "data": body.get("data", date.today().isoformat()),
        "piquete_id": body["piquete_id"],
        "altura_cm": body["altura_cm"],
        "massa_estimada": body.get("massa_estimada"),
        "cobertura_pct": body.get("cobertura_pct"),
        "falhas_pct": body.get("falhas_pct"),
        "planta_invasora": body.get("planta_invasora"),
        "condicao": body.get("condicao"),
        "responsavel": body.get("responsavel"),
        "obs": body.get("obs"),
    }
    result = supabase.table("medicao_pastagem").insert(data).execute().data[0]
    pq_rows = supabase.table("piquetes").select("nome").eq("id", result["piquete_id"]).limit(1).execute().data
    return {"id": result["id"], "data": result["data"], "piquete_nome": pq_rows[0]["nome"] if pq_rows else "", **body}


@router.put("/medicoes/{id}")
def editar_medicao(id: int, body: dict):
    rows = supabase.table("medicao_pastagem").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Medição não encontrada.")
    campos = ["data", "piquete_id", "altura_cm", "massa_estimada", "cobertura_pct",
              "falhas_pct", "planta_invasora", "condicao", "responsavel", "obs"]
    update = {k: body[k] for k in campos if k in body}
    supabase.table("medicao_pastagem").update(update).eq("id", id).execute()
    return {"id": id, "ok": True}


@router.delete("/medicoes/{id}")
def excluir_medicao(id: int):
    rows = supabase.table("medicao_pastagem").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Medição não encontrada.")
    supabase.table("medicao_pastagem").delete().eq("id", id).execute()
    return {"ok": True}


# ── MANEJO (ENTRADAS E SAÍDAS) ───────────────────────────────────────

@router.get("/manejo")
def listar_manejo(
    piquete_id: Optional[int] = Query(None),
    lote: Optional[str] = Query(None),
    data_ini: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    q = supabase.table("manejo_pastagem").select("*")
    if piquete_id:
        q = q.eq("piquete_id", piquete_id)
    if data_ini:
        q = q.gte("data", data_ini)
    if data_fim:
        q = q.lte("data", data_fim)
    rows = q.order("data", desc=True).execute().data

    pq_cache = {}
    result = []
    for m in rows:
        pid = m["piquete_id"]
        if pid not in pq_cache:
            pq_rows = supabase.table("piquetes").select("nome").eq("id", pid).limit(1).execute().data
            pq_cache[pid] = pq_rows[0]["nome"] if pq_rows else ""
        result.append({
            "id": m["id"], "piquete_id": pid,
            "piquete_nome": pq_cache[pid],
            "tipo": m.get("tipo"),
            "lote_id": m.get("lote_id"), "qtd_animais": m.get("qtd_animais"),
            "data": m.get("data"),
            "altura_cm": m.get("altura_cm"),
            "responsavel": m.get("responsavel"),
            "obs": m.get("obs"),
        })
    return result


@router.post("/manejo/entrada")
def registrar_entrada(body: dict):
    piquete_id = body.get("piquete_id")
    if not piquete_id:
        raise HTTPException(status_code=400, detail="piquete_id é obrigatório.")
    pq_rows = supabase.table("piquetes").select("*").eq("id", piquete_id).limit(1).execute().data
    if not pq_rows:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")
    pq = pq_rows[0]

    lote_existente = supabase.table("lotes").select("id").eq("piquete_id", piquete_id).ilike("status", "ATIVO").limit(1).execute().data
    if lote_existente:
        raise HTTPException(status_code=400, detail="Piquete já possui um lote ativo.")

    data_entrada = body.get("data_entrada", date.today().isoformat())
    qtd_animais  = body.get("qtd_animais") or 0
    lote_id      = body.get("lote_id")

    # Last saida date to compute descanso
    last_out = supabase.table("lotes").select("data_saida").eq("piquete_id", piquete_id).not_.is_("data_saida", "null").order("data_saida", desc=True).limit(1).execute().data
    dias_descanso = 0
    if last_out and last_out[0].get("data_saida"):
        try:
            d1 = date.fromisoformat(last_out[0]["data_saida"])
            d2 = date.fromisoformat(data_entrada)
            dias_descanso = max(0, (d2 - d1).days)
        except Exception:
            pass

    previsao = ""
    desc_alvo = pq.get("descanso_alvo_dias")
    if desc_alvo:
        try:
            d_ent = date.fromisoformat(data_entrada)
            previsao = (d_ent + timedelta(days=desc_alvo)).isoformat()
        except Exception:
            pass

    manejo = supabase.table("manejo_pastagem").insert({
        "data": data_entrada,
        "piquete_id": piquete_id,
        "lote_id": lote_id,
        "tipo": "ENTRADA",
        "qtd_animais": qtd_animais,
        "altura_cm": body.get("altura_entrada"),
        "obs": body.get("obs"),
    }).execute().data[0]

    # Mark lote as active in this piquete
    if lote_id:
        supabase.table("lotes").update({
            "piquete_id": piquete_id, "data_entrada": data_entrada, "status": "ATIVO"
        }).eq("id", lote_id).execute()

    supabase.table("piquetes").update({"semaforo": "OCUPADO"}).eq("id", piquete_id).execute()
    return {"id": manejo["id"], "dias_descanso": dias_descanso, "previsao_saida": previsao}


@router.post("/manejo/saida")
def registrar_saida(body: dict):
    manejo_id = body.get("manejo_id")
    if not manejo_id:
        raise HTTPException(status_code=400, detail="manejo_id é obrigatório.")
    manejo_rows = supabase.table("manejo_pastagem").select("*").eq("id", manejo_id).limit(1).execute().data
    if not manejo_rows:
        raise HTTPException(status_code=404, detail="Registro de manejo não encontrado.")
    manejo = manejo_rows[0]

    data_saida = body.get("data_saida", date.today().isoformat())
    dias_ocupacao = 0
    try:
        d1 = date.fromisoformat(manejo.get("data") or "1970-01-01")
        d2 = date.fromisoformat(data_saida)
        dias_ocupacao = max(0, (d2 - d1).days)
    except Exception:
        pass

    ganho_total_kg = 0.0
    lote_id = manejo.get("lote_id")
    if lote_id:
        la_rows = supabase.table("lote_animais").select("brinco").eq("lote_id", lote_id).execute().data
        brincos = [a["brinco"] for a in la_rows]
        if brincos:
            pesagens_rows = supabase.table("pesagens").select("brinco,ganho_kg").gte("data", manejo.get("data","1970-01-01")).lte("data", data_saida).execute().data
            pesagens_filtradas = [p for p in pesagens_rows if p["brinco"] in brincos]
            ganho_total_kg = round(sum(p.get("ganho_kg") or 0 for p in pesagens_filtradas), 2)

    pq_rows = supabase.table("piquetes").select("area_ha").eq("id", manejo["piquete_id"]).limit(1).execute().data
    area_ha = (pq_rows[0]["area_ha"] if pq_rows and pq_rows[0].get("area_ha") else 1) or 1
    ganho_ha_kg = round(ganho_total_kg / area_ha, 2)

    # Record saida event
    supabase.table("manejo_pastagem").insert({
        "data": data_saida,
        "piquete_id": manejo["piquete_id"],
        "lote_id": lote_id,
        "tipo": "SAIDA",
        "altura_cm": body.get("altura_saida"),
        "obs": body.get("obs"),
    }).execute()

    # Mark lote as saiu
    if lote_id:
        supabase.table("lotes").update({"data_saida": data_saida, "status": "INATIVO"}).eq("id", lote_id).eq("piquete_id", manejo["piquete_id"]).execute()

    supabase.table("piquetes").update({"semaforo": "SEM_DADOS"}).eq("id", manejo["piquete_id"]).execute()

    return {
        "dias_ocupacao": dias_ocupacao,
        "ganho_total_kg": ganho_total_kg,
        "ganho_ha_kg": ganho_ha_kg,
    }


# ── ADUBAÇÃO ─────────────────────────────────────────────────────────

@router.get("/adubacao")
def listar_adubacao(
    piquete_id: Optional[int] = Query(None),
    data_ini: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    q = supabase.table("adubacao_pastagem").select("*")
    if piquete_id:
        q = q.eq("piquete_id", piquete_id)
    if data_ini:
        q = q.gte("data", data_ini)
    if data_fim:
        q = q.lte("data", data_fim)
    rows = q.order("data", desc=True).execute().data

    pq_cache = {}
    result = []
    for a in rows:
        pid = a["piquete_id"]
        if pid not in pq_cache:
            pq_rows = supabase.table("piquetes").select("nome").eq("id", pid).limit(1).execute().data
            pq_cache[pid] = pq_rows[0]["nome"] if pq_rows else ""
        result.append({
            "id": a["id"], "data": a["data"], "piquete_id": pid,
            "piquete_nome": pq_cache[pid],
            "produto": a.get("produto"), "dose_kg_ha": a.get("dose_kg_ha"),
            "custo_total": a.get("custo_total"), "responsavel": a.get("responsavel"), "obs": a.get("obs"),
        })
    return result


@router.post("/adubacao")
def criar_adubacao(body: dict):
    if not body.get("piquete_id") or not body.get("produto"):
        raise HTTPException(status_code=400, detail="piquete_id e produto são obrigatórios.")
    data = {
        "data": body.get("data", date.today().isoformat()),
        "piquete_id": body["piquete_id"], "produto": body["produto"],
        "dose_kg_ha": body.get("dose_kg_ha"), "custo_total": body.get("custo_total"),
        "responsavel": body.get("responsavel"), "obs": body.get("obs"),
    }
    result = supabase.table("adubacao_pastagem").insert(data).execute().data[0]
    return {"id": result["id"], "ok": True}


@router.put("/adubacao/{id}")
def editar_adubacao(id: int, body: dict):
    rows = supabase.table("adubacao_pastagem").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Adubação não encontrada.")
    campos = ["data", "piquete_id", "produto", "dose_kg_ha", "custo_total", "responsavel", "obs"]
    update = {k: body[k] for k in campos if k in body}
    supabase.table("adubacao_pastagem").update(update).eq("id", id).execute()
    return {"id": id, "ok": True}


@router.delete("/adubacao/{id}")
def excluir_adubacao(id: int):
    rows = supabase.table("adubacao_pastagem").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Adubação não encontrada.")
    supabase.table("adubacao_pastagem").delete().eq("id", id).execute()
    return {"ok": True}


# ── CHUVA ─────────────────────────────────────────────────────────────

@router.get("/chuva")
def listar_chuva(
    data_ini: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    hoje = date.today()
    q = supabase.table("chuva").select("*")
    if data_ini:
        q = q.gte("data", data_ini)
    if data_fim:
        q = q.lte("data", data_fim)
    rows = q.order("data", desc=True).execute().data

    mes_atual = hoje.strftime("%Y-%m")
    ano_atual = str(hoje.year)
    total_mes = sum(c["mm"] for c in rows if c.get("data") and c["data"][:7] == mes_atual)
    total_ano = sum(c["mm"] for c in rows if c.get("data") and c["data"][:4] == ano_atual)

    return {
        "registros": [{"id": c["id"], "data": c["data"], "area": c.get("area"), "mm": c["mm"], "obs": c.get("obs")} for c in rows],
        "total_mes": round(total_mes, 1),
        "total_ano": round(total_ano, 1),
    }


@router.post("/chuva")
def criar_chuva(body: dict):
    if body.get("mm") is None:
        raise HTTPException(status_code=400, detail="mm é obrigatório.")
    data = {
        "data": body.get("data", date.today().isoformat()),
        "area": body.get("area", "Fazenda Geral"),
        "mm": body["mm"], "obs": body.get("obs"),
    }
    result = supabase.table("chuva").insert(data).execute().data[0]
    return {"id": result["id"], "ok": True}


@router.put("/chuva/{id}")
def editar_chuva(id: int, body: dict):
    rows = supabase.table("chuva").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    update = {k: body[k] for k in ["data", "area", "mm", "obs"] if k in body}
    supabase.table("chuva").update(update).eq("id", id).execute()
    return {"id": id, "ok": True}


@router.delete("/chuva/{id}")
def excluir_chuva(id: int):
    rows = supabase.table("chuva").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    supabase.table("chuva").delete().eq("id", id).execute()
    return {"ok": True}


# ── DASHBOARD ─────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard_pastagem(request: Request):
    fid = get_fazenda_id(request)
    hoje = date.today()

    q = supabase.table("piquetes").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    piquetes = q.execute().data

    semaforos = {"verde": 0, "amarelo": 0, "vermelho": 0,
                 "sair_agora": 0, "ocupado": 0, "sem_dados": 0}
    alertas = []
    taxa_lotacoes = []

    for pq in piquetes:
        s = semaforo_piquete(pq["id"], None)
        cor = s["semaforo"].lower()
        if cor in semaforos:
            semaforos[cor] += 1

        if s["semaforo"] == "SAIR_AGORA":
            alertas.append({"tipo": "SAIR_AGORA", "piquete": pq["nome"], "mensagem": s["mensagem"]})
        elif s["semaforo"] == "SEM_DADOS":
            alertas.append({"tipo": "SEM_DADOS", "piquete": pq["nome"], "mensagem": s["mensagem"]})

        if s["semaforo"] == "OCUPADO" and pq.get("area_ha"):
            lote_rows = supabase.table("lotes").select("ua_ha").eq("piquete_id", pq["id"]).ilike("status", "ATIVO").limit(1).execute().data
            if lote_rows and lote_rows[0].get("ua_ha"):
                taxa_lotacoes.append(lote_rows[0]["ua_ha"])

    taxa_lotacao_media = round(sum(taxa_lotacoes) / len(taxa_lotacoes), 2) if taxa_lotacoes else 0.0

    em_descanso = [pq for pq in piquetes if pq.get("semaforo") not in ("OCUPADO", "VERDE")]
    dias_desc_lista = []
    for pq in em_descanso:
        s = semaforo_piquete(pq["id"], None)
        if s["dias_descanso"]:
            dias_desc_lista.append(s["dias_descanso"])
    dias_descanso_medio = round(sum(dias_desc_lista) / len(dias_desc_lista)) if dias_desc_lista else 0

    lotes_ativos_ganho = supabase.table("lotes").select("id,data_entrada").ilike("status", "ATIVO").not_.is_("piquete_id", "null").execute().data
    ganhos_dia = []
    for lote in lotes_ativos_ganho:
        if lote.get("data_entrada"):
            la_rows = supabase.table("lote_animais").select("brinco").eq("lote_id", lote["id"]).execute().data
            brincos = [a["brinco"] for a in la_rows]
            if brincos:
                pesagens_rows = supabase.table("pesagens").select("brinco,ganho_kg").gte("data", lote.get("data_entrada","1970-01-01")).execute().data
                pesagens_filtradas = [p for p in pesagens_rows if p["brinco"] in brincos]
                total_ganho = sum(p.get("ganho_kg") or 0 for p in pesagens_filtradas)
                try:
                    dias = (hoje - date.fromisoformat(lote["data_entrada"])).days
                    if dias > 0:
                        ganhos_dia.append(total_ganho / dias)
                except Exception:
                    pass
    ganho_medio_diario_kg = round(sum(ganhos_dia) / len(ganhos_dia), 2) if ganhos_dia else 0.0

    d90 = (hoje - timedelta(days=90)).isoformat()
    adubs = supabase.table("adubacao_pastagem").select("custo_total").gte("data", d90).execute().data
    custo_total_adub = sum(a.get("custo_total") or 0 for a in adubs)
    area_total = sum(pq.get("area_ha") or 0 for pq in piquetes)
    custo_adubacao_ha = round(custo_total_adub / area_total, 2) if area_total else 0.0

    mes_atual = hoje.strftime("%Y-%m")
    ano_atual = str(hoje.year)
    q_chuva = supabase.table("chuva").select("data,mm")
    if fid > 0:
        q_chuva = q_chuva.eq("fazenda_id", fid)
    chuvas_todas = q_chuva.execute().data
    chuva_mes = round(sum(c["mm"] for c in chuvas_todas if c.get("data") and c["data"][:7] == mes_atual), 1)
    chuva_ano = round(sum(c["mm"] for c in chuvas_todas if c.get("data") and c["data"][:4] == ano_atual), 1)
    if chuva_mes < 50:
        alertas.append({"tipo": "SECA", "piquete": "Geral",
                        "mensagem": f"Apenas {chuva_mes} mm no mês. Risco de seca!"})

    manejo_rows = []  # ganho_ha_kg/ua_total not in Supabase manejo_pastagem schema
    ganho_por_piquete = defaultdict(list)
    ua_por_piquete = defaultdict(list)
    for m in manejo_rows:
        pid = m["piquete_id"]
        if m.get("ganho_ha_kg") is not None:
            ganho_por_piquete[pid].append(m["ganho_ha_kg"])
        if m.get("ua_total") is not None:
            ua_por_piquete[pid].append(m["ua_total"])
    ranking = []
    for pid in ganho_por_piquete:
        ganhos = ganho_por_piquete[pid]
        uas = ua_por_piquete.get(pid, [])
        pq_rows = supabase.table("piquetes").select("nome,area_ha").eq("id", pid).limit(1).execute().data
        nome = pq_rows[0]["nome"] if pq_rows else str(pid)
        ranking.append({
            "nome": nome,
            "ganho_ha_kg": round(sum(ganhos) / len(ganhos), 2),
            "ciclos": len(ganhos),
        })
    ranking.sort(key=lambda x: x["ganho_ha_kg"], reverse=True)
    ranking = ranking[:5]

    lotes_todos = supabase.table("lotes").select("*").eq("status", "ATIVO").execute().data
    lotes_em_piquete = [l for l in lotes_todos if l.get("piquete_id")]
    ua_has_lotes = [l["ua_ha"] for l in lotes_em_piquete if l.get("ua_ha")]
    lotes_criticos = sum(1 for l in lotes_todos if l.get("classificacao") == "CRÍTICA")
    lotacao_media_lotes = round(sum(ua_has_lotes) / len(ua_has_lotes), 2) if ua_has_lotes else 0.0

    lotes_kpi = {
        "total_ativos": len(lotes_todos),
        "em_piquete": len(lotes_em_piquete),
        "sem_piquete": len(lotes_todos) - len(lotes_em_piquete),
        "lotacao_media_uaha": lotacao_media_lotes,
        "alertas_criticos": lotes_criticos,
    }

    return {
        "semaforos": semaforos,
        "taxa_lotacao_media": taxa_lotacao_media,
        "dias_descanso_medio": dias_descanso_medio,
        "ganho_medio_diario_kg": ganho_medio_diario_kg,
        "custo_adubacao_ha": custo_adubacao_ha,
        "chuva_mes_mm": chuva_mes,
        "chuva_ano_mm": chuva_ano,
        "ranking_piquetes": ranking,
        "alertas": alertas,
        "lotes": lotes_kpi,
    }


# ── RELATÓRIOS ────────────────────────────────────────────────────────

@router.get("/relatorios/ranking")
def ranking_piquetes():
    hoje = date.today()
    d90 = (hoje - timedelta(days=90)).isoformat()

    manejo_rows = []  # ganho_ha_kg/ua_total not in Supabase manejo_pastagem schema
    ganho_por_piquete = defaultdict(list)
    ua_por_piquete = defaultdict(list)
    for m in manejo_rows:
        pid = m["piquete_id"]
        if m.get("ganho_ha_kg") is not None:
            ganho_por_piquete[pid].append(m["ganho_ha_kg"])
        if m.get("ua_total") is not None:
            ua_por_piquete[pid].append(m["ua_total"])

    result = []
    for pid in ganho_por_piquete:
        ganhos = ganho_por_piquete[pid]
        uas = ua_por_piquete.get(pid, [])
        pq_rows = supabase.table("piquetes").select("nome,area_ha").eq("id", pid).limit(1).execute().data
        nome = pq_rows[0]["nome"] if pq_rows else str(pid)
        area = (pq_rows[0]["area_ha"] if pq_rows and pq_rows[0].get("area_ha") else 1) or 1

        adub_rows = supabase.table("adubacao_pastagem").select("custo_total").eq("piquete_id", pid).gte("data", d90).execute().data
        custo_adub = sum(a.get("custo_total") or 0 for a in adub_rows)

        ua_media = (sum(uas) / len(uas)) if uas else 0
        result.append({
            "piquete": nome,
            "ciclos": len(ganhos),
            "ganho_ha_medio": round(sum(ganhos) / len(ganhos), 2),
            "lotacao_media": round(ua_media / area, 2),
            "custo_adubacao_ha": round(custo_adub / area, 2),
        })

    result.sort(key=lambda x: x["ganho_ha_medio"], reverse=True)
    return result


@router.get("/relatorios/chuva-mensal")
def chuva_mensal():
    hoje = date.today()
    resultado = {}
    for i in range(11, -1, -1):
        mes = hoje.month - i
        ano = hoje.year
        while mes <= 0:
            mes += 12
            ano -= 1
        chave = f"{ano}-{mes:02d}"
        rows = supabase.table("chuva").select("mm").like("data", f"{chave}%").execute().data
        resultado[chave] = round(sum(c["mm"] or 0 for c in rows), 1)
    return resultado


@router.get("/relatorios/adubacao-historico")
def adubacao_historico():
    rows = supabase.table("adubacao_pastagem").select("*").order("data", desc=True).execute().data
    pq_cache = {}
    result = []
    for a in rows:
        pid = a["piquete_id"]
        if pid not in pq_cache:
            pq_rows = supabase.table("piquetes").select("nome").eq("id", pid).limit(1).execute().data
            pq_cache[pid] = pq_rows[0]["nome"] if pq_rows else ""
        result.append({
            "id": a["id"], "piquete": pq_cache[pid], "data": a["data"],
            "produto": a.get("produto"), "dose_kg_ha": a.get("dose_kg_ha"), "custo_total": a.get("custo_total"),
        })
    return result


@router.get("/relatorios/comparativo")
def comparativo_piquetes():
    hoje = date.today()
    meses = []
    for i in range(5, -1, -1):
        mes = hoje.month - i
        ano = hoje.year
        while mes <= 0:
            mes += 12
            ano -= 1
        meses.append(f"{ano}-{mes:02d}")

    piquetes = supabase.table("piquetes").select("id,nome").order("nome").execute().data
    manejo_rows = []  # ganho_ha_kg/data_entrada not in Supabase manejo_pastagem schema

    tabela = []
    for pq in piquetes:
        linha = {"piquete": pq["nome"]}
        for chave in meses:
            relevant = [m for m in manejo_rows
                        if m["piquete_id"] == pq["id"]
                        and m.get("data_entrada") and m["data_entrada"][:7] == chave
                        and m.get("ganho_ha_kg") is not None]
            if relevant:
                linha[chave] = round(sum(m["ganho_ha_kg"] for m in relevant) / len(relevant), 2)
            else:
                linha[chave] = 0.0
        tabela.append(linha)
    return {"meses": meses, "tabela": tabela}


# ── Helpers de Lotes ─────────────────────────────────────────────────

def _classificar_ua_ha(ua_ha) -> str:
    if ua_ha is None:
        return "SEM_DADOS"
    if ua_ha <= 1.5:
        return "LEVE"
    if ua_ha <= 3.0:
        return "IDEAL"
    if ua_ha <= 4.5:
        return "ALTA"
    return "CRITICA"


def _recalcular_lote(db, lote_id: int):
    membros = supabase.table("lote_animais").select("brinco").eq("lote_id", lote_id).is_("data_saida", "null").execute().data
    ua_total = 0.0
    for m in membros:
        animal_rows = supabase.table("animais").select("peso_atual").ilike("brinco", m["brinco"]).limit(1).execute().data
        if animal_rows and animal_rows[0].get("peso_atual"):
            ua_total += round(animal_rows[0]["peso_atual"] / 450, 3)
    ua_total = round(ua_total, 2)

    lote_rows = supabase.table("lotes").select("piquete_id").eq("id", lote_id).limit(1).execute().data
    piquete_id = lote_rows[0]["piquete_id"] if lote_rows and lote_rows[0].get("piquete_id") else None

    ua_ha = None
    if piquete_id:
        pq_rows = supabase.table("piquetes").select("area_ha").eq("id", piquete_id).limit(1).execute().data
        if pq_rows and pq_rows[0].get("area_ha"):
            ua_ha = round(ua_total / pq_rows[0]["area_ha"], 2)

    classificacao = _classificar_ua_ha(ua_ha)
    supabase.table("lotes").update({"ua_total": ua_total, "ua_ha": ua_ha, "classificacao": classificacao}).eq("id", lote_id).execute()


def _lote_dict(db, lote: dict) -> dict:
    lote_id = lote["id"]
    membros = supabase.table("lote_animais").select("brinco").eq("lote_id", lote_id).is_("data_saida", "null").execute().data
    pq = None
    if lote.get("piquete_id"):
        pq_rows = supabase.table("piquetes").select("nome").eq("id", lote["piquete_id"]).limit(1).execute().data
        pq = pq_rows[0] if pq_rows else None
    return {
        "id": lote_id,
        "nome": lote["nome"],
        "categoria": lote.get("categoria"),
        "descricao": lote.get("descricao"),
        "piquete_id": lote.get("piquete_id"),
        "piquete_nome": pq["nome"] if pq else None,
        "status": lote.get("status"),
        "ua_total": lote.get("ua_total"),
        "ua_ha": lote.get("ua_ha"),
        "classificacao": lote.get("classificacao"),
        "qtd_animais": len(membros),
        "criado_em": lote.get("criado_em"),
    }


# ── Endpoints de Lotes ───────────────────────────────────────────────

@router.get("/lotes/simular")
def simular_lotacao(piquete_id: int, brincos: str):
    pq_rows = supabase.table("piquetes").select("*").eq("id", piquete_id).limit(1).execute().data
    if not pq_rows:
        raise HTTPException(404, "Piquete não encontrado")
    pq = pq_rows[0]

    lista = [b.strip() for b in brincos.split(",") if b.strip()]
    ua_total = 0.0
    for brinco in lista:
        animal_rows = supabase.table("animais").select("peso_atual").ilike("brinco", brinco).limit(1).execute().data
        if animal_rows and animal_rows[0].get("peso_atual"):
            ua_total += animal_rows[0]["peso_atual"] / 450

    ua_ha = round(ua_total / pq["area_ha"], 2) if pq.get("area_ha") else None
    return {
        "piquete_id": piquete_id,
        "area_ha": pq.get("area_ha"),
        "qtd_animais": len(lista),
        "ua_total": round(ua_total, 2),
        "ua_ha": ua_ha,
        "classificacao": _classificar_ua_ha(ua_ha),
    }


@router.get("/lotes")
def listar_lotes():
    lotes = supabase.table("lotes").select("*").order("nome").execute().data
    return [_lote_dict(None, lt) for lt in lotes]


@router.get("/lotes/{lote_id}")
def obter_lote(lote_id: int):
    rows = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    return _lote_dict(None, rows[0])


@router.post("/lotes", status_code=201)
def criar_lote(payload: dict):
    existing = supabase.table("lotes").select("id").eq("nome", payload.get("nome")).limit(1).execute().data
    if existing:
        raise HTTPException(400, "Já existe um lote com esse nome")
    data = {
        "nome": payload["nome"],
        "categoria": payload.get("categoria"),
        "descricao": payload.get("descricao"),
        "piquete_id": payload.get("piquete_id"),
        "status": payload.get("status", "ATIVO"),
    }
    lote = supabase.table("lotes").insert(data).execute().data[0]
    _recalcular_lote(None, lote["id"])
    lote = supabase.table("lotes").select("*").eq("id", lote["id"]).limit(1).execute().data[0]
    return _lote_dict(None, lote)


@router.put("/lotes/{lote_id}")
def atualizar_lote(lote_id: int, payload: dict):
    rows = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    update = {k: payload[k] for k in ("nome", "categoria", "descricao", "status") if k in payload}
    if update:
        supabase.table("lotes").update(update).eq("id", lote_id).execute()
    _recalcular_lote(None, lote_id)
    lote = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data[0]
    return _lote_dict(None, lote)


@router.delete("/lotes/{lote_id}")
def excluir_lote(lote_id: int):
    rows = supabase.table("lotes").select("id").eq("id", lote_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    membros = supabase.table("lote_animais").select("id").eq("lote_id", lote_id).is_("data_saida", "null").execute().data
    if membros:
        raise HTTPException(400, "Remova os animais do lote antes de excluir")
    supabase.table("lote_animais").delete().eq("lote_id", lote_id).execute()
    supabase.table("lotes").delete().eq("id", lote_id).execute()
    return {"ok": True}


@router.get("/lotes/{lote_id}/animais")
def listar_animais_lote(lote_id: int):
    rows = supabase.table("lotes").select("id").eq("id", lote_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    membros = supabase.table("lote_animais").select("brinco,data_entrada").eq("lote_id", lote_id).is_("data_saida", "null").execute().data
    resultado = []
    for m in membros:
        a_rows = supabase.table("animais").select("nome,tipo,peso_atual").ilike("brinco", m["brinco"]).limit(1).execute().data
        a = a_rows[0] if a_rows else None
        resultado.append({
            "brinco": m["brinco"],
            "nome": a["nome"] if a else None,
            "tipo": a["tipo"] if a else None,
            "peso_atual": a["peso_atual"] if a else None,
            "ua": round((a["peso_atual"] or 0) / 450, 3) if a and a.get("peso_atual") else 0,
            "data_entrada": m.get("data_entrada"),
        })
    return resultado


@router.post("/lotes/{lote_id}/animais")
def adicionar_animal_lote(lote_id: int, payload: dict):
    rows = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    brinco = (payload.get("brinco") or "").strip().upper()
    if not brinco:
        raise HTTPException(400, "brinco obrigatório")
    animal_rows = supabase.table("animais").select("id").ilike("brinco", brinco).limit(1).execute().data
    if not animal_rows:
        raise HTTPException(404, f"Animal {brinco} não encontrado")
    existente = supabase.table("lote_animais").select("id").eq("lote_id", lote_id).ilike("brinco", brinco).is_("data_saida", "null").limit(1).execute().data
    if existente:
        raise HTTPException(400, "Animal já está neste lote")
    supabase.table("lote_animais").insert({
        "lote_id": lote_id,
        "brinco": brinco,
        "data_entrada": payload.get("data_entrada", date.today().strftime("%Y-%m-%d")),
        "status": "ATIVO",
    }).execute()
    _recalcular_lote(None, lote_id)
    lote = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data[0]
    return _lote_dict(None, lote)


@router.delete("/lotes/{lote_id}/animais/{brinco}")
def remover_animal_lote(lote_id: int, brinco: str):
    rows = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    membro = supabase.table("lote_animais").select("id").eq("lote_id", lote_id).ilike("brinco", brinco.upper()).is_("data_saida", "null").limit(1).execute().data
    if not membro:
        raise HTTPException(404, "Animal não encontrado no lote")
    supabase.table("lote_animais").update({
        "status": "SAIU",
        "data_saida": date.today().strftime("%Y-%m-%d"),
    }).eq("id", membro[0]["id"]).execute()
    _recalcular_lote(None, lote_id)
    lote = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data[0]
    return _lote_dict(None, lote)


@router.post("/lotes/{lote_id}/alocar")
def alocar_lote_piquete(lote_id: int, payload: dict):
    rows = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    piquete_id = payload.get("piquete_id")
    pq_rows = supabase.table("piquetes").select("id").eq("id", piquete_id).limit(1).execute().data
    if not pq_rows:
        raise HTTPException(404, "Piquete não encontrado")
    supabase.table("lotes").update({"piquete_id": piquete_id}).eq("id", lote_id).execute()
    _recalcular_lote(None, lote_id)
    lote = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data[0]
    return _lote_dict(None, lote)


@router.post("/lotes/{lote_id}/desalocar")
def desalocar_lote_piquete(lote_id: int):
    rows = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    supabase.table("lotes").update({
        "piquete_id": None,
        "ua_ha": None,
        "classificacao": _classificar_ua_ha(None),
    }).eq("id", lote_id).execute()
    lote = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data[0]
    return _lote_dict(None, lote)
