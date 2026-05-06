from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from database import supabase, get_fazenda_id

router = APIRouter()


# ── HELPERS ──────────────────────────────────────────────────────────────

def _status_gmd(gmd):
    if gmd is None: return 'SEM_DADOS'
    if gmd > 1.4: return 'EXCELENTE'
    if gmd >= 1.0: return 'BOM'
    if gmd >= 0.7: return 'REGULAR'
    return 'RUIM'

def _status_ca(ca):
    if ca is None: return 'SEM_DADOS'
    if ca < 6: return 'EXCELENTE'
    if ca <= 8: return 'BOM'
    if ca <= 12: return 'REGULAR'
    return 'RUIM'

def _status_giro(dias):
    if dias <= 120: return 'OK'
    if dias <= 150: return 'ATENCAO'
    return 'CRITICO'


def _calcular_dieta_totais(dieta_id: int, db=None) -> dict:
    items = supabase.table("dieta_ingredientes").select("*").eq("dieta_id", dieta_id).execute().data
    ms_total = 0.0
    custo_total = 0.0
    vol_kg = conc_kg = min_kg = adi_kg = 0.0
    total_kg = 0.0
    for item in items:
        ing_rows = supabase.table("ingredientes_dieta").select("*").eq("id", item["ingrediente_id"]).limit(1).execute().data
        if not ing_rows:
            continue
        ing = ing_rows[0]
        ms = item["kg_cab_dia"] * (ing["pct_ms"] / 100.0)
        custo = item["kg_cab_dia"] * ing["preco_kg"]
        ms_total += ms
        custo_total += custo
        total_kg += item["kg_cab_dia"]
        tipo = ing.get("tipo", "")
        if tipo == 'VOLUMOSO': vol_kg += item["kg_cab_dia"]
        elif tipo == 'CONCENTRADO': conc_kg += item["kg_cab_dia"]
        elif tipo == 'MINERAL': min_kg += item["kg_cab_dia"]
        else: adi_kg += item["kg_cab_dia"]
    pct_vol  = round(vol_kg  / total_kg * 100, 1) if total_kg else 0
    pct_conc = round(conc_kg / total_kg * 100, 1) if total_kg else 0
    pct_min  = round(min_kg  / total_kg * 100, 1) if total_kg else 0
    return {
        'ms_total_cab_dia': round(ms_total, 3),
        'custo_cab_dia': round(custo_total, 4),
        'total_kg_cab_dia': round(total_kg, 3),
        'pct_volumoso': pct_vol,
        'pct_concentrado': pct_conc,
        'pct_mineral': pct_min,
    }


def _calcular_lote_kpis(lote: dict, db=None) -> dict:
    hoje = date.today()
    try:
        dt_entrada = date.fromisoformat(lote["data_entrada"])
    except Exception:
        dt_entrada = hoje
    dias = max((hoje - dt_entrada).days, 1)

    ultima_pes_rows = supabase.table("pesagem_confinamento").select("peso_medio_kg").eq("lote_conf_id", lote["id"]).order("data", desc=True).limit(1).execute().data
    peso_atual = ultima_pes_rows[0]["peso_medio_kg"] if ultima_pes_rows else lote["peso_medio_entrada"]

    ganho_total_cab = peso_atual - lote["peso_medio_entrada"]
    gmd = round(ganho_total_cab / dias, 3) if dias > 0 else 0

    lancamentos = supabase.table("lancamento_confinamento").select("ms_fornecida_kg,custo_real").eq("lote_conf_id", lote["id"]).execute().data
    total_ms = sum(l.get("ms_fornecida_kg") or 0 for l in lancamentos)
    custo_nutricao = sum(l.get("custo_real") or 0 for l in lancamentos)

    qtd_animais = lote.get("qtd_animais") or 1
    ganho_total_lote = ganho_total_cab * qtd_animais
    ca = round(total_ms / ganho_total_lote, 2) if ganho_total_lote > 0 else None
    cms_cab_dia = round(total_ms / qtd_animais / dias, 2) if qtd_animais and dias > 0 else None
    cms_pct_pv = round(cms_cab_dia / peso_atual * 100, 2) if cms_cab_dia and peso_atual else None

    custo_aquisicao = (lote.get("valor_compra_cab") or 0) * qtd_animais
    custo_frete = (lote.get("frete_entrada") or 0) + (lote.get("frete_saida") or 0)
    custo_mao_obra = (lote.get("mao_obra_cab_dia") or 0) * qtd_animais * dias
    custo_outros = lote.get("outros_custos") or 0
    custo_total = custo_aquisicao + custo_nutricao + custo_frete + custo_mao_obra + custo_outros

    rc_est = lote.get("rc_estimado_pct") or 54
    peso_alvo = lote.get("peso_alvo_saida") or 0
    arrobas_proj = (peso_alvo * rc_est / 100 * qtd_animais) / 15
    receita_proj = arrobas_proj * (lote.get("preco_arroba_venda") or 0)
    lucro_proj = receita_proj - custo_total
    custo_arroba_proj = round(custo_total / arrobas_proj, 2) if arrobas_proj else None

    dias_restantes = None
    data_saida_prev = None
    if gmd > 0 and peso_alvo:
        dias_restantes = round((peso_alvo - peso_atual) / gmd)
        if dias_restantes >= 0:
            data_saida_prev = (hoje + timedelta(days=dias_restantes)).isoformat()

    fase_rows = supabase.table("fases_confinamento").select("*").eq("lote_conf_id", lote["id"]).eq("status", "ATIVA").limit(1).execute().data
    fase_ativa = fase_rows[0] if fase_rows else None

    return {
        'dias_confinamento': dias,
        'peso_atual': round(peso_atual, 1),
        'ganho_total_cab': round(ganho_total_cab, 1),
        'gmd': gmd,
        'ca': ca,
        'cms_cab_dia': cms_cab_dia,
        'cms_pct_pv': cms_pct_pv,
        'total_ms_kg': round(total_ms, 1),
        'custo_nutricao': round(custo_nutricao, 2),
        'custo_aquisicao': round(custo_aquisicao, 2),
        'custo_frete': round(custo_frete, 2),
        'custo_mao_obra': round(custo_mao_obra, 2),
        'custo_outros': round(custo_outros, 2),
        'custo_total': round(custo_total, 2),
        'custo_cab_total': round(custo_total / qtd_animais, 2) if qtd_animais else 0,
        'arrobas_proj': round(arrobas_proj, 1),
        'custo_arroba_proj': custo_arroba_proj,
        'receita_proj': round(receita_proj, 2),
        'lucro_proj': round(lucro_proj, 2),
        'lucro_proj_cab': round(lucro_proj / qtd_animais, 2) if qtd_animais else 0,
        'dias_restantes': dias_restantes,
        'data_saida_prevista': data_saida_prev,
        'status_gmd': _status_gmd(gmd),
        'status_ca': _status_ca(ca),
        'status_giro': _status_giro(dias),
        'fase_atual': {
            'id': fase_ativa["id"],
            'fase': fase_ativa["fase"],
            'dieta_id': fase_ativa["dieta_id"],
            'data_inicio': fase_ativa["data_inicio"],
            'duracao_prevista': fase_ativa.get("duracao_prevista"),
        } if fase_ativa else None,
    }


# ── INGREDIENTES ──────────────────────────────────────────────────────────

@router.get("/ingredientes")
def listar_ingredientes(
    tipo: Optional[str] = Query(None),
    ativo: Optional[bool] = Query(None),
):
    q = supabase.table("ingredientes_dieta").select("*")
    if tipo:
        q = q.eq("tipo", tipo.upper())
    if ativo is not None:
        q = q.eq("ativo", ativo)
    return q.order("tipo").order("nome").execute().data


@router.post("/ingredientes", status_code=201)
def criar_ingrediente(body: dict):
    nome = (body.get("nome") or "").strip()
    if not nome:
        raise HTTPException(400, "Nome é obrigatório")
    pct_ms = float(body.get("pct_ms") or 0)
    if not (0 < pct_ms <= 100):
        raise HTTPException(400, "pct_ms deve ser entre 1 e 100")
    existing = supabase.table("ingredientes_dieta").select("id").ilike("nome", nome).limit(1).execute().data
    if existing:
        raise HTTPException(400, "Ingrediente já cadastrado com este nome")
    data = {
        "nome": nome, "tipo": (body.get("tipo") or "CONCENTRADO").upper(),
        "pct_ms": pct_ms, "preco_kg": float(body.get("preco_kg") or 0),
        "energia_mcal": body.get("energia_mcal"), "proteina_pct": body.get("proteina_pct"),
        "unidade": body.get("unidade", "kg"), "ativo": body.get("ativo", True),
        "obs": body.get("obs"),
    }
    return supabase.table("ingredientes_dieta").insert(data).execute().data[0]


@router.put("/ingredientes/{id}")
def editar_ingrediente(id: int, body: dict):
    rows = supabase.table("ingredientes_dieta").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Ingrediente não encontrado")
    campos = ["nome","tipo","pct_ms","energia_mcal","proteina_pct","preco_kg","unidade","ativo","obs"]
    update = {k: body[k] for k in campos if k in body}
    supabase.table("ingredientes_dieta").update(update).eq("id", id).execute()
    return supabase.table("ingredientes_dieta").select("*").eq("id", id).limit(1).execute().data[0]


@router.delete("/ingredientes/{id}")
def excluir_ingrediente(id: int):
    rows = supabase.table("ingredientes_dieta").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Ingrediente não encontrado")
    em_uso = supabase.table("dieta_ingredientes").select("id").eq("ingrediente_id", id).limit(1).execute().data
    if em_uso:
        raise HTTPException(400, "Ingrediente está em uso em uma dieta")
    supabase.table("ingredientes_dieta").delete().eq("id", id).execute()
    return {"ok": True}


# ── DIETAS ───────────────────────────────────────────────────────────────

def _dieta_out(dieta: dict) -> dict:
    items = supabase.table("dieta_ingredientes").select("*").eq("dieta_id", dieta["id"]).order("ordem").execute().data
    ingredientes_out = []
    for item in items:
        ing_rows = supabase.table("ingredientes_dieta").select("*").eq("id", item["ingrediente_id"]).limit(1).execute().data
        if ing_rows:
            ing = ing_rows[0]
            ms = round(item["kg_cab_dia"] * ing["pct_ms"] / 100, 3)
            custo = round(item["kg_cab_dia"] * ing["preco_kg"], 4)
            ingredientes_out.append({
                "id": item["id"], "ingrediente_id": ing["id"], "nome": ing["nome"],
                "tipo": ing["tipo"], "pct_ms": ing["pct_ms"], "preco_kg": ing["preco_kg"],
                "kg_cab_dia": item["kg_cab_dia"], "ms_cab_dia": ms,
                "custo_cab_dia": custo, "ordem": item.get("ordem"),
            })
    totais = _calcular_dieta_totais(dieta["id"])
    return {
        "id": dieta["id"], "nome": dieta["nome"], "fase": dieta.get("fase"),
        "duracao_dias": dieta.get("duracao_dias"), "obs": dieta.get("obs"), "ativo": dieta.get("ativo"),
        "ingredientes": ingredientes_out,
        **totais,
    }


@router.get("/dietas")
def listar_dietas():
    dietas = supabase.table("dietas_confinamento").select("*").order("fase").order("nome").execute().data
    return [_dieta_out(d) for d in dietas]


@router.post("/dietas", status_code=201)
def criar_dieta(body: dict):
    nome = (body.get("nome") or "").strip()
    if not nome:
        raise HTTPException(400, "Nome é obrigatório")
    existing = supabase.table("dietas_confinamento").select("id").ilike("nome", nome).limit(1).execute().data
    if existing:
        raise HTTPException(400, "Dieta já cadastrada com este nome")
    dieta = supabase.table("dietas_confinamento").insert({
        "nome": nome, "fase": (body.get("fase") or "CRESCIMENTO").upper(),
        "duracao_dias": body.get("duracao_dias"), "obs": body.get("obs"), "ativo": True,
    }).execute().data[0]
    for i, item in enumerate(body.get("ingredientes") or []):
        supabase.table("dieta_ingredientes").insert({
            "dieta_id": dieta["id"], "ingrediente_id": int(item["ingrediente_id"]),
            "kg_cab_dia": float(item["kg_cab_dia"]), "ordem": i,
        }).execute()
    return _dieta_out(dieta)


@router.put("/dietas/{id}")
def editar_dieta(id: int, body: dict):
    rows = supabase.table("dietas_confinamento").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Dieta não encontrada")
    update = {k: body[k] for k in ["nome","fase","duracao_dias","obs","ativo"] if k in body}
    if update:
        supabase.table("dietas_confinamento").update(update).eq("id", id).execute()
    if "ingredientes" in body:
        supabase.table("dieta_ingredientes").delete().eq("dieta_id", id).execute()
        for i, item in enumerate(body["ingredientes"] or []):
            supabase.table("dieta_ingredientes").insert({
                "dieta_id": id, "ingrediente_id": int(item["ingrediente_id"]),
                "kg_cab_dia": float(item["kg_cab_dia"]), "ordem": i,
            }).execute()
    dieta = supabase.table("dietas_confinamento").select("*").eq("id", id).limit(1).execute().data[0]
    return _dieta_out(dieta)


@router.delete("/dietas/{id}")
def excluir_dieta(id: int):
    rows = supabase.table("dietas_confinamento").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Dieta não encontrada")
    em_uso = supabase.table("fases_confinamento").select("id").eq("dieta_id", id).eq("status", "ATIVA").limit(1).execute().data
    if em_uso:
        raise HTTPException(400, "Dieta em uso em fase ativa")
    supabase.table("dieta_ingredientes").delete().eq("dieta_id", id).execute()
    supabase.table("dietas_confinamento").delete().eq("id", id).execute()
    return {"ok": True}


@router.get("/dietas/simular")
def simular_dieta(
    dieta_id: int = Query(...),
    qtd_animais: int = Query(...),
    dias: int = Query(...),
    peso_medio_kg: float = Query(400.0),
):
    rows = supabase.table("dietas_confinamento").select("id").eq("id", dieta_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Dieta não encontrada")
    totais = _calcular_dieta_totais(dieta_id)
    ms_cab_dia = totais["ms_total_cab_dia"]
    custo_cab_dia = totais["custo_cab_dia"]
    ms_total = round(ms_cab_dia * qtd_animais * dias, 1)
    custo_total = round(custo_cab_dia * qtd_animais * dias, 2)
    cms_pct_pv = round(ms_cab_dia / peso_medio_kg * 100, 2) if peso_medio_kg else None
    return {
        "dieta_id": dieta_id,
        "qtd_animais": qtd_animais, "dias": dias, "peso_medio_kg": peso_medio_kg,
        "custo_cab_dia": custo_cab_dia,
        "custo_total": custo_total,
        "ms_total": ms_total,
        "ms_cab_dia": ms_cab_dia,
        "cms_cab_pct_pv": cms_pct_pv,
        "custo_cab_fase": round(custo_cab_dia * dias, 2),
    }


# ── LOTES DE CONFINAMENTO ─────────────────────────────────────────────────

@router.get("/lotes")
def listar_lotes(
    request: Request,
    status: Optional[str] = Query(None),
):
    fid = get_fazenda_id(request)
    q = supabase.table("lotes_confinamento").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    if status:
        q = q.ilike("status", status)
    lotes = q.order("data_entrada", desc=True).execute().data
    result = []
    for lote in lotes:
        d = dict(lote)
        d.update(_calcular_lote_kpis(lote))
        if d.get("fase_atual"):
            diet_rows = supabase.table("dietas_confinamento").select("nome").eq("id", d["fase_atual"]["dieta_id"]).limit(1).execute().data
            if diet_rows:
                d["fase_atual"]["dieta_nome"] = diet_rows[0]["nome"]
        result.append(d)
    return result


@router.post("/lotes", status_code=201)
def criar_lote(request: Request, body: dict):
    fid = get_fazenda_id(request)
    nome = (body.get("nome") or "").strip()
    if not nome:
        raise HTTPException(400, "Nome é obrigatório")
    lote_data = {
        "fazenda_id": fid if fid > 0 else 1,
        "nome": nome,
        "data_entrada": body.get("data_entrada", date.today().isoformat()),
        "qtd_animais": int(body.get("qtd_animais") or 0),
        "peso_medio_entrada": float(body.get("peso_medio_entrada") or 0),
        "peso_alvo_saida": float(body.get("peso_alvo_saida") or 0),
        "valor_compra_cab": float(body.get("valor_compra_cab") or 0),
        "frete_entrada": float(body.get("frete_entrada") or 0),
        "frete_saida": float(body.get("frete_saida") or 0),
        "mao_obra_cab_dia": float(body.get("mao_obra_cab_dia") or 0),
        "outros_custos": float(body.get("outros_custos") or 0),
        "preco_arroba_venda": body.get("preco_arroba_venda"),
        "rc_estimado_pct": float(body.get("rc_estimado_pct") or 54),
        "status": 'ATIVO',
        "obs": body.get("obs"),
    }
    lote = supabase.table("lotes_confinamento").insert(lote_data).execute().data[0]

    dt_ini = date.fromisoformat(lote["data_entrada"])
    for fase_data in (body.get("fases") or []):
        supabase.table("fases_confinamento").insert({
            "lote_conf_id": lote["id"],
            "dieta_id": int(fase_data["dieta_id"]),
            "fase": fase_data["fase"].upper(),
            "data_inicio": dt_ini.isoformat(),
            "duracao_prevista": int(fase_data.get("duracao_prevista") or 0),
            "status": 'ATIVA' if dt_ini == date.fromisoformat(lote["data_entrada"]) else 'AGUARDANDO',
        }).execute()
        dt_ini += timedelta(days=int(fase_data.get("duracao_prevista") or 0))

    d = dict(lote)
    d.update(_calcular_lote_kpis(lote))
    return d


@router.put("/lotes/{id}")
def editar_lote(id: int, body: dict):
    rows = supabase.table("lotes_confinamento").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    campos = ["frete_saida","preco_arroba_venda","rc_real_pct","outros_custos","status","obs","mao_obra_cab_dia"]
    update = {k: body[k] for k in campos if k in body}
    if update:
        supabase.table("lotes_confinamento").update(update).eq("id", id).execute()
    lote = supabase.table("lotes_confinamento").select("*").eq("id", id).limit(1).execute().data[0]
    d = dict(lote)
    d.update(_calcular_lote_kpis(lote))
    return d


@router.delete("/lotes/{id}")
def excluir_lote(id: int):
    rows = supabase.table("lotes_confinamento").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    lote = rows[0]
    if lote.get("status") != 'ATIVO':
        raise HTTPException(400, "Só é possível excluir lotes com status ATIVO")
    tem_lanc = supabase.table("lancamento_confinamento").select("id").eq("lote_conf_id", id).limit(1).execute().data
    if tem_lanc:
        raise HTTPException(400, "Lote possui lançamentos. Exclua os lançamentos antes.")
    supabase.table("fases_confinamento").delete().eq("lote_conf_id", id).execute()
    supabase.table("pesagem_confinamento").delete().eq("lote_conf_id", id).execute()
    supabase.table("lotes_confinamento").delete().eq("id", id).execute()
    return {"ok": True}


@router.post("/lotes/{id}/encerrar")
def encerrar_lote(id: int, body: dict):
    rows = supabase.table("lotes_confinamento").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    lote = rows[0]

    data_saida = body.get("data_saida_real", date.today().isoformat())
    peso_saida = float(body.get("peso_medio_saida") or 0)
    rc_real = float(body.get("rc_real_pct") or lote.get("rc_estimado_pct") or 54)
    preco_arr = float(body.get("preco_arroba_venda") or lote.get("preco_arroba_venda") or 0)
    frete_saida = float(body.get("frete_saida") or 0)

    supabase.table("lotes_confinamento").update({
        "data_saida_real": data_saida,
        "rc_real_pct": rc_real,
        "preco_arroba_venda": preco_arr,
        "frete_saida": frete_saida,
        "status": 'ENCERRADO',
    }).eq("id", id).execute()

    fase_rows = supabase.table("fases_confinamento").select("id").eq("lote_conf_id", id).eq("status", "ATIVA").limit(1).execute().data
    if fase_rows:
        supabase.table("fases_confinamento").update({"status": "CONCLUIDA", "data_fim": data_saida}).eq("id", fase_rows[0]["id"]).execute()

    lote_updated = supabase.table("lotes_confinamento").select("*").eq("id", id).limit(1).execute().data[0]
    kpis = _calcular_lote_kpis(lote_updated)
    peso_carcaca = peso_saida * rc_real / 100
    arrobas = (peso_carcaca * lote_updated["qtd_animais"]) / 15
    receita = arrobas * preco_arr

    if preco_arr > 0 and lote_updated["qtd_animais"] > 0:
        try:
            dt = date.fromisoformat(data_saida)
            supabase.table("vendas").insert({
                "lote": lote_updated["nome"],
                "descricao": f"Venda do lote de confinamento {lote_updated['nome']}",
                "data": data_saida,
                "valor_unit": round(preco_arr, 2),
                "quantidade": round(arrobas, 2),
                "valor_total": round(receita, 2),
                "mes": dt.month, "ano": dt.year,
            }).execute()
        except Exception:
            pass

    d = dict(lote_updated)
    d.update(kpis)
    d["peso_saida_real"] = peso_saida
    d["rc_real_pct"] = rc_real
    d["arrobas_reais"] = round(arrobas, 1)
    d["receita_real"] = round(receita, 2)
    return d


# ── FASES ─────────────────────────────────────────────────────────────────

@router.get("/lotes/{id}/fases")
def listar_fases(id: int):
    fases = supabase.table("fases_confinamento").select("*").eq("lote_conf_id", id).order("data_inicio").execute().data
    result = []
    for f in fases:
        d = dict(f)
        diet_rows = supabase.table("dietas_confinamento").select("nome").eq("id", f["dieta_id"]).limit(1).execute().data
        d["dieta_nome"] = diet_rows[0]["nome"] if diet_rows else None
        d["dieta_totais"] = _calcular_dieta_totais(f["dieta_id"])
        result.append(d)
    return result


@router.post("/lotes/{id}/fases/avancar")
def avancar_fase(id: int, body: dict):
    rows = supabase.table("lotes_confinamento").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lote não encontrado")
    fase_rows = supabase.table("fases_confinamento").select("*").eq("lote_conf_id", id).eq("status", "ATIVA").limit(1).execute().data
    if not fase_rows:
        raise HTTPException(400, "Nenhuma fase ativa neste lote")
    fase_ativa = fase_rows[0]

    hoje_str = date.today().isoformat()
    supabase.table("fases_confinamento").update({"status": "CONCLUIDA", "data_fim": hoje_str}).eq("id", fase_ativa["id"]).execute()

    nova_dieta_id = body.get("dieta_id")
    nova_fase = body.get("fase", "TERMINACAO")
    nova_duracao = body.get("duracao_prevista")
    if nova_dieta_id:
        supabase.table("fases_confinamento").insert({
            "lote_conf_id": id,
            "dieta_id": int(nova_dieta_id),
            "fase": nova_fase.upper(),
            "data_inicio": hoje_str,
            "duracao_prevista": int(nova_duracao) if nova_duracao else None,
            "status": 'ATIVA',
        }).execute()
    return {"ok": True, "fase_concluida": fase_ativa["fase"]}


# ── LANÇAMENTOS ───────────────────────────────────────────────────────────

@router.get("/lancamentos")
def listar_lancamentos(
    lote_conf_id: Optional[int] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
):
    q = supabase.table("lancamento_confinamento").select("*")
    if lote_conf_id:
        q = q.eq("lote_conf_id", lote_conf_id)
    if data_inicio:
        q = q.gte("data", data_inicio)
    if data_fim:
        q = q.lte("data", data_fim)
    return q.order("data", desc=True).execute().data


def _calcular_lancamento(lote_conf_id: int, fase_id: int, qtd_kg: float, db=None) -> dict:
    fase_rows = supabase.table("fases_confinamento").select("*").eq("id", fase_id).limit(1).execute().data
    if not fase_rows:
        return {"ms_fornecida_kg": 0, "custo_real": 0, "qtd_planejada_kg": 0}
    fase = fase_rows[0]
    lote_rows = supabase.table("lotes_confinamento").select("qtd_animais").eq("id", lote_conf_id).limit(1).execute().data
    lote_qtd = lote_rows[0]["qtd_animais"] if lote_rows else 1
    items = supabase.table("dieta_ingredientes").select("*").eq("dieta_id", fase["dieta_id"]).execute().data
    ms_pct_medio = 0.0
    custo_pct = 0.0
    total_plano_kg = sum(item["kg_cab_dia"] for item in items)
    if total_plano_kg > 0:
        for item in items:
            ing_rows = supabase.table("ingredientes_dieta").select("pct_ms,preco_kg").eq("id", item["ingrediente_id"]).limit(1).execute().data
            if not ing_rows:
                continue
            ing = ing_rows[0]
            prop = item["kg_cab_dia"] / total_plano_kg
            ms_pct_medio += prop * (ing["pct_ms"] / 100)
            custo_pct += prop * ing["preco_kg"]
    ms_fornecida = round(qtd_kg * ms_pct_medio, 3)
    custo_real = round(qtd_kg * custo_pct, 2)
    qtd_planejada = round(total_plano_kg * lote_qtd, 1)
    return {
        "ms_fornecida_kg": ms_fornecida,
        "custo_real": custo_real,
        "qtd_planejada_kg": qtd_planejada,
    }


@router.post("/lancamentos", status_code=201)
def criar_lancamento(body: dict):
    lote_conf_id = int(body.get("lote_conf_id") or 0)
    fase_id = int(body.get("fase_id") or 0)
    qtd = float(body.get("qtd_fornecida_kg") or 0)
    if not lote_conf_id or not fase_id or not qtd:
        raise HTTPException(400, "lote_conf_id, fase_id e qtd_fornecida_kg são obrigatórios")
    calc = _calcular_lancamento(lote_conf_id, fase_id, qtd)
    return supabase.table("lancamento_confinamento").insert({
        "lote_conf_id": lote_conf_id, "fase_id": fase_id,
        "data": body.get("data", date.today().isoformat()),
        "qtd_fornecida_kg": qtd,
        "qtd_planejada_kg": calc["qtd_planejada_kg"],
        "ms_fornecida_kg": calc["ms_fornecida_kg"],
        "custo_real": calc["custo_real"],
        "responsavel": body.get("responsavel"),
        "obs": body.get("obs"),
    }).execute().data[0]


@router.put("/lancamentos/{id}")
def editar_lancamento(id: int, body: dict):
    rows = supabase.table("lancamento_confinamento").select("*").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lançamento não encontrado")
    lanc = rows[0]
    update = {}
    if "qtd_fornecida_kg" in body:
        qtd = float(body["qtd_fornecida_kg"])
        calc = _calcular_lancamento(lanc["lote_conf_id"], lanc["fase_id"], qtd)
        update["qtd_fornecida_kg"] = qtd
        update["ms_fornecida_kg"] = calc["ms_fornecida_kg"]
        update["custo_real"] = calc["custo_real"]
    for c in ["data","responsavel","obs"]:
        if c in body:
            update[c] = body[c]
    if update:
        supabase.table("lancamento_confinamento").update(update).eq("id", id).execute()
    return supabase.table("lancamento_confinamento").select("*").eq("id", id).limit(1).execute().data[0]


@router.delete("/lancamentos/{id}")
def excluir_lancamento(id: int):
    rows = supabase.table("lancamento_confinamento").select("id").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lançamento não encontrado")
    supabase.table("lancamento_confinamento").delete().eq("id", id).execute()
    return {"ok": True}


# ── PESAGENS DO LOTE ─────────────────────────────────────────────────────

@router.get("/lotes/{id}/pesagens")
def listar_pesagens_lote(id: int):
    return supabase.table("pesagem_confinamento").select("*").eq("lote_conf_id", id).order("data").execute().data


@router.post("/lotes/{id}/pesagens", status_code=201)
def criar_pesagem_lote(id: int, body: dict):
    lote_rows = supabase.table("lotes_confinamento").select("*").eq("id", id).limit(1).execute().data
    if not lote_rows:
        raise HTTPException(404, "Lote não encontrado")
    lote = lote_rows[0]
    data = body.get("data", date.today().isoformat())
    peso = float(body.get("peso_medio_kg") or 0)
    qtd = int(body.get("qtd_animais") or lote["qtd_animais"])

    anterior_rows = supabase.table("pesagem_confinamento").select("*").eq("lote_conf_id", id).order("data", desc=True).limit(1).execute().data
    anterior = anterior_rows[0] if anterior_rows else None

    gmd_periodo = None
    ca_periodo = None
    cms_cab_dia = None

    if anterior:
        try:
            dt_ant = date.fromisoformat(anterior["data"])
            dt_atual = date.fromisoformat(data)
            dias_periodo = max((dt_atual - dt_ant).days, 1)
            ganho_cab = peso - anterior["peso_medio_kg"]
            gmd_periodo = round(ganho_cab / dias_periodo, 3) if dias_periodo > 0 else None
            ms_rows = supabase.table("lancamento_confinamento").select("ms_fornecida_kg").eq("lote_conf_id", id).gt("data", anterior["data"]).lte("data", data).execute().data
            ms_periodo = sum(r.get("ms_fornecida_kg") or 0 for r in ms_rows)
            ganho_total = ganho_cab * qtd
            ca_periodo = round(ms_periodo / ganho_total, 2) if ganho_total > 0 else None
            cms_cab_dia = round(ms_periodo / qtd / dias_periodo, 2) if qtd and dias_periodo > 0 else None
        except Exception:
            pass
    else:
        try:
            dt_entrada = date.fromisoformat(lote["data_entrada"])
            dt_atual = date.fromisoformat(data)
            dias_periodo = max((dt_atual - dt_entrada).days, 1)
            ganho_cab = peso - lote["peso_medio_entrada"]
            gmd_periodo = round(ganho_cab / dias_periodo, 3) if dias_periodo > 0 else None
            ms_rows = supabase.table("lancamento_confinamento").select("ms_fornecida_kg").eq("lote_conf_id", id).lte("data", data).execute().data
            ms_periodo = sum(r.get("ms_fornecida_kg") or 0 for r in ms_rows)
            ganho_total = ganho_cab * qtd
            ca_periodo = round(ms_periodo / ganho_total, 2) if ganho_total > 0 else None
            cms_cab_dia = round(ms_periodo / qtd / dias_periodo, 2) if qtd and dias_periodo > 0 else None
        except Exception:
            pass

    return supabase.table("pesagem_confinamento").insert({
        "lote_conf_id": id, "data": data, "peso_medio_kg": peso,
        "qtd_animais": qtd, "gmd_periodo": gmd_periodo,
        "ca_periodo": ca_periodo, "cms_cab_dia": cms_cab_dia,
        "responsavel": body.get("responsavel"), "obs": body.get("obs"),
    }).execute().data[0]


# ── DASHBOARD ─────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard_confinamento(request: Request):
    fid = get_fazenda_id(request)
    q = supabase.table("lotes_confinamento").select("*").eq("status", "ATIVO")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    lotes_ativos = q.execute().data

    animais_total = sum(l.get("qtd_animais") or 0 for l in lotes_ativos)
    gmds = []
    cas = []
    custo_dia = 0.0
    lucro_total = 0.0
    proxima_saida = None
    alertas = []

    for lote in lotes_ativos:
        kpis = _calcular_lote_kpis(lote)
        if kpis["gmd"] and kpis["gmd"] > 0:
            gmds.append(kpis["gmd"])
        if kpis["ca"]:
            cas.append(kpis["ca"])
        if kpis.get("fase_atual"):
            totais_fase = _calcular_dieta_totais(kpis["fase_atual"]["dieta_id"])
            custo_dia += totais_fase["custo_cab_dia"] * (lote.get("qtd_animais") or 0)
        lucro_total += kpis.get("lucro_proj") or 0

        if kpis.get("data_saida_prevista"):
            if not proxima_saida or kpis["data_saida_prevista"] < proxima_saida["data"]:
                proxima_saida = {
                    "lote": lote["nome"],
                    "data": kpis["data_saida_prevista"],
                    "dias": kpis.get("dias_restantes"),
                }

        if kpis["gmd"] and kpis["gmd"] < 0.7:
            alertas.append({"tipo": "GMD_BAIXO", "lote": lote["nome"], "valor": kpis["gmd"]})
        if kpis["dias_confinamento"] > 150:
            alertas.append({"tipo": "GIRO_LONGO", "lote": lote["nome"], "dias": kpis["dias_confinamento"]})

    return {
        "lotes_ativos": len(lotes_ativos),
        "animais_confinados": animais_total,
        "gmd_medio": round(sum(gmds) / len(gmds), 2) if gmds else None,
        "ca_medio": round(sum(cas) / len(cas), 2) if cas else None,
        "custo_dia_total": round(custo_dia, 2),
        "lucro_proj_total": round(lucro_total, 2),
        "proxima_saida": proxima_saida,
        "alertas": alertas,
    }


# ── ANIMAIS DO LOTE ──────────────────────────────────────────────────────

@router.get("/lotes/{id}/animais")
def listar_animais_lote(id: int):
    lote_rows = supabase.table("lotes_confinamento").select("*").eq("id", id).limit(1).execute().data
    if not lote_rows:
        raise HTTPException(404, "Lote não encontrado")
    lote = lote_rows[0]

    hoje = date.today()
    try:
        dt_entrada = date.fromisoformat(lote["data_entrada"])
    except Exception:
        dt_entrada = hoje
    dias_conf = max((hoje - dt_entrada).days, 1)

    brincos = {}

    for a in supabase.table("animais").select("*").eq("lote", lote["nome"]).eq("status", "ATIVO").execute().data:
        brincos[a["brinco"]] = a

    lote_past_rows = supabase.table("lotes").select("id").eq("nome", lote["nome"]).limit(1).execute().data
    if lote_past_rows:
        for la in supabase.table("lote_animais").select("brinco").eq("lote_id", lote_past_rows[0]["id"]).eq("status", "ATIVO").execute().data:
            if la["brinco"] not in brincos:
                a_rows = supabase.table("animais").select("*").ilike("brinco", la["brinco"]).limit(1).execute().data
                if a_rows:
                    brincos[a_rows[0]["brinco"]] = a_rows[0]

    pci_brincos = supabase.table("pesagem_conf_individual").select("brinco").eq("lote_conf_id", id).execute().data
    for item in pci_brincos:
        br = item["brinco"]
        if br not in brincos:
            a_rows = supabase.table("animais").select("*").ilike("brinco", br).limit(1).execute().data
            if a_rows:
                brincos[a_rows[0]["brinco"]] = a_rows[0]

    result = []
    for a in brincos.values():
        ult_pci_rows = supabase.table("pesagem_conf_individual").select("*").eq("lote_conf_id", id).ilike("brinco", a["brinco"]).order("data", desc=True).order("id", desc=True).limit(1).execute().data
        ult_pci = ult_pci_rows[0] if ult_pci_rows else None

        peso_atual = ult_pci["peso_kg"] if ult_pci else (a.get("peso_atual") or lote["peso_medio_entrada"])
        ult_data = ult_pci["data"] if ult_pci else None
        try:
            dias_desde_ultima = (hoje - date.fromisoformat(ult_data)).days if ult_data else dias_conf
        except Exception:
            dias_desde_ultima = dias_conf

        pes_ent_rows = supabase.table("pesagens").select("peso").ilike("brinco", a["brinco"]).lte("data_pesagem", lote["data_entrada"]).order("data_pesagem", desc=True).limit(1).execute().data
        peso_entrada = pes_ent_rows[0]["peso"] if pes_ent_rows else lote["peso_medio_entrada"]

        ganho = peso_atual - peso_entrada
        gmd_acum = round(ganho / dias_conf, 3) if dias_conf > 0 else 0
        falta = max(0.0, (lote.get("peso_alvo_saida") or 0) - peso_atual)
        dias_rest = round(falta / gmd_acum) if gmd_acum > 0 else None
        dt_saida = (hoje + timedelta(days=dias_rest)).isoformat() if dias_rest is not None else None

        result.append({
            "brinco": a["brinco"], "nome": a.get("nome"), "tipo": a.get("tipo"), "raca": a.get("raca"),
            "peso_entrada": round(float(peso_entrada), 1),
            "peso_atual": round(float(peso_atual), 1),
            "ultima_pesagem": ult_data,
            "dias_desde_ultima": dias_desde_ultima,
            "gmd_acumulado": gmd_acum,
            "dias_confinamento": dias_conf,
            "peso_alvo": lote.get("peso_alvo_saida"),
            "falta_kg": round(falta, 1),
            "dias_restantes": dias_rest,
            "data_saida_prevista": dt_saida,
            "status_gmd": _status_gmd(gmd_acum),
        })

    result.sort(key=lambda x: x["gmd_acumulado"] or 0, reverse=True)
    return result


# ── PESAGENS INDIVIDUAIS ──────────────────────────────────────────────────

@router.get("/lotes/{id}/pesagens/individuais")
def listar_pesagens_individuais(id: int):
    pcis = supabase.table("pesagem_conf_individual").select("*").eq("lote_conf_id", id).order("data", desc=True).order("brinco").execute().data
    result = []
    for p in pcis:
        a_rows = supabase.table("animais").select("nome").ilike("brinco", p["brinco"]).limit(1).execute().data
        d = dict(p)
        d["nome_animal"] = a_rows[0]["nome"] if a_rows else None
        result.append(d)
    return result


@router.post("/lotes/{id}/pesagens/individuais", status_code=201)
def registrar_pesagens_individuais(id: int, body: dict):
    lote_rows = supabase.table("lotes_confinamento").select("*").eq("id", id).limit(1).execute().data
    if not lote_rows:
        raise HTTPException(404, "Lote não encontrado")
    lote = lote_rows[0]

    data_pes = body.get("data", date.today().isoformat())
    responsavel = body.get("responsavel")
    pesagens_input = body.get("pesagens", [])

    salvos = 0
    erros = []
    pesos_salvos = []
    gmds_salvos = []

    for item in pesagens_input:
        brinco = (item.get("brinco") or "").strip()
        try:
            peso_novo = float(item.get("peso_kg") or 0)
        except Exception:
            peso_novo = 0
        if not brinco or peso_novo <= 0:
            erros.append({"brinco": brinco, "erro": "Dados inválidos"})
            continue

        animal_rows = supabase.table("animais").select("id").ilike("brinco", brinco).limit(1).execute().data
        if not animal_rows:
            erros.append({"brinco": brinco, "erro": "Animal não encontrado"})
            continue

        ant_rows = supabase.table("pesagem_conf_individual").select("*").eq("lote_conf_id", id).ilike("brinco", brinco).lt("data", data_pes).order("data", desc=True).limit(1).execute().data
        ant_pci = ant_rows[0] if ant_rows else None

        gmd_periodo = None
        dias_periodo = None

        if ant_pci:
            try:
                dias_periodo = max((date.fromisoformat(data_pes) - date.fromisoformat(ant_pci["data"])).days, 1)
                gmd_periodo = round((peso_novo - ant_pci["peso_kg"]) / dias_periodo, 3)
            except Exception:
                pass
        else:
            pes_ant_rows = supabase.table("pesagens").select("peso,data_pesagem").ilike("brinco", brinco).lt("data_pesagem", data_pes).order("data_pesagem", desc=True).limit(1).execute().data
            if pes_ant_rows:
                try:
                    dias_periodo = max((date.fromisoformat(data_pes) - date.fromisoformat(pes_ant_rows[0]["data_pesagem"])).days, 1)
                    gmd_periodo = round((peso_novo - pes_ant_rows[0]["peso"]) / dias_periodo, 3)
                except Exception:
                    pass

        supabase.table("pesagem_conf_individual").insert({
            "lote_conf_id": id, "brinco": brinco, "data": data_pes,
            "peso_kg": peso_novo, "gmd_periodo": gmd_periodo,
            "dias_periodo": dias_periodo, "responsavel": responsavel,
        }).execute()
        supabase.table("animais").update({"peso_atual": peso_novo}).ilike("brinco", brinco).execute()

        salvos += 1
        pesos_salvos.append(peso_novo)
        if gmd_periodo is not None:
            gmds_salvos.append(gmd_periodo)

    peso_medio_lote = round(sum(pesos_salvos) / len(pesos_salvos), 1) if pesos_salvos else None
    gmd_medio_lote = round(sum(gmds_salvos) / len(gmds_salvos), 2) if gmds_salvos else None
    gmd_max = round(max(gmds_salvos), 2) if gmds_salvos else None
    gmd_min = round(min(gmds_salvos), 2) if gmds_salvos else None
    animais_abaixo_meta = sum(1 for g in gmds_salvos if g < 1.0)

    if peso_medio_lote:
        ult_lote_rows = supabase.table("pesagem_confinamento").select("id").eq("lote_conf_id", id).eq("data", data_pes).limit(1).execute().data
        if ult_lote_rows:
            supabase.table("pesagem_confinamento").update({"peso_medio_kg": peso_medio_lote, "qtd_animais": salvos}).eq("id", ult_lote_rows[0]["id"]).execute()
        else:
            supabase.table("pesagem_confinamento").insert({
                "lote_conf_id": id, "data": data_pes,
                "peso_medio_kg": peso_medio_lote,
                "qtd_animais": salvos, "responsavel": responsavel,
            }).execute()

    return {
        "salvos": salvos,
        "erros": erros,
        "peso_medio_lote": peso_medio_lote,
        "gmd_medio_lote": gmd_medio_lote,
        "gmd_max": gmd_max,
        "gmd_min": gmd_min,
        "animais_abaixo_meta": animais_abaixo_meta,
    }


# ── SEED ──────────────────────────────────────────────────────────────────

def seed_confinamento(db=None):
    existing = supabase.table("ingredientes_dieta").select("id").limit(1).execute().data
    if existing:
        return

    ingredientes_data = [
        dict(nome="Silagem de Milho",  tipo="VOLUMOSO",    pct_ms=32, preco_kg=0.35),
        dict(nome="Cana Picada",       tipo="VOLUMOSO",    pct_ms=28, preco_kg=0.12),
        dict(nome="Milho Moído",       tipo="CONCENTRADO", pct_ms=88, preco_kg=1.45),
        dict(nome="Farelo de Soja",    tipo="CONCENTRADO", pct_ms=88, preco_kg=3.80),
        dict(nome="Ureia Pecuária",    tipo="CONCENTRADO", pct_ms=98, preco_kg=4.20),
        dict(nome="Núcleo Mineral",    tipo="MINERAL",     pct_ms=98, preco_kg=6.50),
        dict(nome="Caroço de Algodão", tipo="VOLUMOSO",    pct_ms=92, preco_kg=1.80),
        dict(nome="Polpa Cítrica",     tipo="CONCENTRADO", pct_ms=88, preco_kg=1.20),
    ]
    ing_ids = {}
    for i in ingredientes_data:
        result = supabase.table("ingredientes_dieta").insert(i).execute().data[0]
        ing_ids[i["nome"]] = result["id"]

    dieta_adap  = supabase.table("dietas_confinamento").insert({"nome": "Adaptação 14d",  "fase": "ADAPTACAO",   "duracao_dias": 14}).execute().data[0]
    dieta_cresc = supabase.table("dietas_confinamento").insert({"nome": "Crescimento",    "fase": "CRESCIMENTO", "duracao_dias": 30}).execute().data[0]
    dieta_term  = supabase.table("dietas_confinamento").insert({"nome": "Terminação",     "fase": "TERMINACAO",  "duracao_dias": 46}).execute().data[0]

    for d_id, nome, kg, ordem in [
        (dieta_adap["id"],  "Silagem de Milho", 10.0, 0),
        (dieta_adap["id"],  "Milho Moído",       1.5, 1),
        (dieta_adap["id"],  "Núcleo Mineral",    0.2, 2),
        (dieta_cresc["id"], "Silagem de Milho",  8.0, 0),
        (dieta_cresc["id"], "Milho Moído",        2.5, 1),
        (dieta_cresc["id"], "Farelo de Soja",    0.8, 2),
        (dieta_cresc["id"], "Núcleo Mineral",    0.2, 3),
        (dieta_term["id"],  "Silagem de Milho",  6.0, 0),
        (dieta_term["id"],  "Milho Moído",        4.0, 1),
        (dieta_term["id"],  "Farelo de Soja",    1.2, 2),
        (dieta_term["id"],  "Caroço de Algodão", 1.5, 3),
        (dieta_term["id"],  "Núcleo Mineral",    0.2, 4),
    ]:
        supabase.table("dieta_ingredientes").insert({"dieta_id": d_id, "ingrediente_id": ing_ids[nome], "kg_cab_dia": kg, "ordem": ordem}).execute()

    hoje = date.today()
    entrada = (hoje - timedelta(days=30)).isoformat()
    lote_ex = supabase.table("lotes_confinamento").insert({
        "fazenda_id": 1, "nome": "Engorda Abril/26",
        "data_entrada": entrada,
        "qtd_animais": 20, "peso_medio_entrada": 380.0, "peso_alvo_saida": 480.0,
        "valor_compra_cab": 2800.0, "frete_entrada": 400.0,
        "mao_obra_cab_dia": 1.50, "rc_estimado_pct": 54.0, "status": "ATIVO",
    }).execute().data[0]

    dt_entrada = date.fromisoformat(entrada)
    dt_adap_fim = dt_entrada + timedelta(days=14)
    supabase.table("fases_confinamento").insert({
        "lote_conf_id": lote_ex["id"], "dieta_id": dieta_adap["id"],
        "fase": "ADAPTACAO", "data_inicio": entrada,
        "data_fim": dt_adap_fim.isoformat(), "duracao_prevista": 14, "status": "CONCLUIDA",
    }).execute()
    fase_cresc = supabase.table("fases_confinamento").insert({
        "lote_conf_id": lote_ex["id"], "dieta_id": dieta_cresc["id"],
        "fase": "CRESCIMENTO", "data_inicio": dt_adap_fim.isoformat(),
        "duracao_prevista": 30, "status": "ATIVA",
    }).execute().data[0]

    for i in range(10):
        dt = hoje - timedelta(days=10 - i)
        supabase.table("lancamento_confinamento").insert({
            "lote_conf_id": lote_ex["id"], "fase_id": fase_cresc["id"],
            "data": dt.isoformat(), "qtd_fornecida_kg": 230.0,
            "qtd_planejada_kg": 230.0,
            "ms_fornecida_kg": round(230 * 0.346, 1),
            "custo_real": round(230 * 0.95, 2),
        }).execute()

    supabase.table("pesagem_confinamento").insert({
        "lote_conf_id": lote_ex["id"], "data": entrada, "peso_medio_kg": 380.0, "qtd_animais": 20,
    }).execute()
    supabase.table("pesagem_confinamento").insert({
        "lote_conf_id": lote_ex["id"],
        "data": (dt_entrada + timedelta(days=15)).isoformat(),
        "peso_medio_kg": 395.0, "qtd_animais": 20, "gmd_periodo": 1.0,
    }).execute()
