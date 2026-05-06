from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from database import supabase, get_fazenda_id

router = APIRouter()

# ── Tipos válidos ─────────────────────────────────────────────────────────────
_TIPOS_VALIDOS = {
    "SAL_MINERAL", "SAL_PROTEINADO", "PROT_ENERGETICO",
    "RACAO_SEMICONFINADO", "VOLUMOSO_SILAGEM", "CONCENTRADO_LEITE",
}

# ── Helpers de cálculo ────────────────────────────────────────────────────────

def _calc_consumo(sup: dict, peso_medio_kg: float, qtd_animais: int):
    """Retorna (g_min/cab, g_max/cab, g_med/cab).
    pct_min/pct_max são frações do PV (ex: 0.001 = 1g/kg = 0.1% PV).
    g_min_fixo/g_max_fixo são g/cab/dia fixos (Sal Mineral).
    """
    if sup.get("pct_min") is not None and sup.get("pct_max") is not None:
        g_min = sup["pct_min"] * peso_medio_kg * 1000
        g_max = sup["pct_max"] * peso_medio_kg * 1000
    else:
        g_min = sup.get("g_min_fixo") or 0.0
        g_max = sup.get("g_max_fixo") or g_min
    g_med = (g_min + g_max) / 2
    return round(g_min, 1), round(g_max, 1), round(g_med, 1)


def _custo_estimado(g_med: float, qtd_animais: int, preco_kg: float):
    consumo_kg_dia = g_med / 1000 * qtd_animais
    custo_dia = consumo_kg_dia * preco_kg
    return round(custo_dia, 2), round(custo_dia * 30, 2)


def _saldo_estoque(suplemento_id: int, fazenda_id: Optional[int] = None) -> float:
    q = supabase.table("estoque_suplemento").select("tipo_mov,quantidade_kg").eq("suplemento_id", suplemento_id)
    if fazenda_id:
        q = q.eq("fazenda_id", fazenda_id)
    rows = q.execute().data
    saldo = 0.0
    for r in rows:
        if r["tipo_mov"] in ("ENTRADA", "AJUSTE"):
            saldo += r["quantidade_kg"]
        else:
            saldo -= r["quantidade_kg"]
    return round(saldo, 3)


def _consumo_medio_diario(suplemento_id: int, dias: int = 30, fazenda_id: Optional[int] = None) -> Optional[float]:
    data_ini = (date.today() - timedelta(days=dias)).isoformat()
    q = (supabase.table("lancamento_racao").select("qtd_fornecida_kg,data")
         .eq("suplemento_id", suplemento_id).gte("data", data_ini))
    if fazenda_id:
        q = q.eq("fazenda_id", fazenda_id)
    rows = q.execute().data
    if not rows:
        return None
    total_kg = sum(r["qtd_fornecida_kg"] for r in rows)
    dias_distintos = len(set(r["data"] for r in rows))
    return round(total_kg / max(dias_distintos, 1), 3)


def _status_estoque(saldo_kg: float, cmd: Optional[float]) -> tuple:
    if cmd and cmd > 0:
        dias = round(saldo_kg / cmd, 1)
        sit = "CRITICO" if dias < 7 else ("BAIXO" if dias < 15 else "OK")
    else:
        dias, sit = None, "SEM_DADOS"
    return dias, sit


def _ca_classificacao(ca: Optional[float]) -> str:
    if ca is None:
        return "SEM_DADOS"
    if ca < 6:
        return "EXCELENTE"
    if ca < 8:
        return "BOM"
    if ca < 12:
        return "REGULAR"
    return "RUIM"


# ── SUPLEMENTOS ───────────────────────────────────────────────────────────────

@router.get("/suplementos")
def listar_suplementos(tipo: Optional[str] = None, ativo: Optional[bool] = None):
    q = supabase.table("suplementos").select("*").order("nome")
    if tipo:
        q = q.eq("tipo", tipo)
    if ativo is not None:
        q = q.eq("ativo", ativo)
    rows = q.execute().data
    result = []
    for s in rows:
        saldo = _saldo_estoque(s["id"])
        cmd = _consumo_medio_diario(s["id"])
        dias, sit = _status_estoque(saldo, cmd)
        result.append({**s, "saldo_kg": saldo, "dias_restantes": dias, "situacao_estoque": sit})
    return result


@router.post("/suplementos", status_code=201)
def criar_suplemento(body: dict):
    nome = body.get("nome", "").strip()
    if not nome:
        raise HTTPException(400, "Campo obrigatório: nome")
    preco = body.get("preco_kg")
    if not preco or float(preco) <= 0:
        raise HTTPException(400, "preco_kg deve ser > 0")
    existing = supabase.table("suplementos").select("id").ilike("nome", nome).limit(1).execute().data
    if existing:
        raise HTTPException(400, "Nome de suplemento já cadastrado")
    allowed = {
        "nome", "tipo", "fabricante", "preco_kg", "pct_min", "pct_max",
        "g_min_fixo", "g_max_fixo", "objetivo", "ativo", "obs",
    }
    data = {k: v for k, v in body.items() if k in allowed}
    data.setdefault("ativo", True)
    result = supabase.table("suplementos").insert(data).execute().data[0]
    return {"id": result["id"], "ok": True}


@router.put("/suplementos/{sid}")
def editar_suplemento(sid: int, body: dict):
    rows = supabase.table("suplementos").select("id").eq("id", sid).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Suplemento não encontrado")
    allowed = {
        "nome", "tipo", "fabricante", "preco_kg", "pct_min", "pct_max",
        "g_min_fixo", "g_max_fixo", "objetivo", "ativo", "obs",
    }
    data = {k: v for k, v in body.items() if k in allowed}
    supabase.table("suplementos").update(data).eq("id", sid).execute()
    return {"ok": True}


@router.delete("/suplementos/{sid}")
def excluir_suplemento(sid: int):
    rows = supabase.table("suplementos").select("id").eq("id", sid).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Suplemento não encontrado")
    planos_ativos = supabase.table("plano_nutricional").select("id").eq("suplemento_id", sid).eq("status", "ATIVO").limit(1).execute().data
    if planos_ativos:
        raise HTTPException(400, "Não é possível excluir: suplemento tem planos ativos")
    supabase.table("suplementos").delete().eq("id", sid).execute()
    return {"ok": True}


# ── SIMULADOR ─────────────────────────────────────────────────────────────────

@router.get("/simular")
def simular(
    suplemento_id: int = Query(...),
    peso_medio_kg: float = Query(...),
    qtd_animais: int = Query(...),
    preco_kg: Optional[float] = Query(None),
):
    sup_rows = supabase.table("suplementos").select("*").eq("id", suplemento_id).limit(1).execute().data
    if not sup_rows:
        raise HTTPException(404, "Suplemento não encontrado")
    sup = sup_rows[0]
    preco = preco_kg or sup["preco_kg"]
    g_min, g_max, g_med = _calc_consumo(sup, peso_medio_kg, qtd_animais)

    lote_min_kg = round(g_min / 1000 * qtd_animais, 3)
    lote_max_kg = round(g_max / 1000 * qtd_animais, 3)
    lote_med_kg = round(g_med / 1000 * qtd_animais, 3)

    custo_min_cab = round(g_min / 1000 * preco, 4)
    custo_max_cab = round(g_max / 1000 * preco, 4)
    custo_med_cab = round(g_med / 1000 * preco, 4)
    custo_min_lote = round(custo_min_cab * qtd_animais, 2)
    custo_max_lote = round(custo_max_cab * qtd_animais, 2)
    custo_med_lote = round(custo_med_cab * qtd_animais, 2)

    saldo = _saldo_estoque(suplemento_id)
    dias_estoque = round(saldo / lote_med_kg, 1) if lote_med_kg > 0 else None

    return {
        "tipo": sup["tipo"],
        "objetivo": sup.get("objetivo"),
        "consumo_min_g_cab": g_min,
        "consumo_max_g_cab": g_max,
        "consumo_med_g_cab": g_med,
        "consumo_min_lote_kg": lote_min_kg,
        "consumo_max_lote_kg": lote_max_kg,
        "consumo_med_lote_kg": lote_med_kg,
        "custo_min_cab_dia": custo_min_cab,
        "custo_max_cab_dia": custo_max_cab,
        "custo_med_cab_dia": custo_med_cab,
        "custo_min_lote_dia": custo_min_lote,
        "custo_max_lote_dia": custo_max_lote,
        "custo_med_lote_dia": custo_med_lote,
        "custo_med_lote_mes": round(custo_med_lote * 30, 2),
        "estoque_atual_kg": saldo,
        "dias_estoque": dias_estoque,
        "alerta_estoque": (dias_estoque is not None and dias_estoque < 15),
    }


# ── PLANOS NUTRICIONAIS ───────────────────────────────────────────────────────

@router.get("/planos")
def listar_planos(
    request: Request,
    lote_id: Optional[int] = None,
    status: Optional[str] = None,
    suplemento_id: Optional[int] = None,
):
    fid = get_fazenda_id(request)
    q = supabase.table("plano_nutricional").select("*").order("data_inicio", desc=True)
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    if lote_id:
        q = q.eq("lote_id", lote_id)
    if status:
        q = q.eq("status", status)
    if suplemento_id:
        q = q.eq("suplemento_id", suplemento_id)
    planos = q.execute().data
    result = []
    hoje = date.today().isoformat()
    for p in planos:
        sup_rows  = supabase.table("suplementos").select("nome,tipo").eq("id", p["suplemento_id"]).limit(1).execute().data
        lote_rows = supabase.table("lotes").select("nome").eq("id", p["lote_id"]).limit(1).execute().data

        # Consumo real do período
        lancs = supabase.table("lancamento_racao").select("qtd_fornecida_kg,custo_real,data").eq("plano_id", p["id"]).gte("data", p["data_inicio"]).execute().data
        consumo_real_total = round(sum(l["qtd_fornecida_kg"] for l in lancs), 3)
        custo_real_total   = round(sum((l.get("custo_real") or 0) for l in lancs), 2)

        # Consumo planejado no período
        dias_plano = (date.fromisoformat(hoje) - date.fromisoformat(p["data_inicio"])).days + 1
        consumo_med_lote_dia = p.get("consumo_med_g", 0) / 1000 * p.get("qtd_animais", 0)
        consumo_plan_total   = round(consumo_med_lote_dia * dias_plano, 3)

        # Consumo de hoje
        lancs_hoje = [l for l in lancs if l["data"] == hoje]
        consumo_hoje = round(sum(l["qtd_fornecida_kg"] for l in lancs_hoje), 3)

        # CA do período (pesagens)
        lote_brincos = supabase.table("lote_animais").select("brinco").eq("lote_id", p["lote_id"]).execute().data
        brincos = [la["brinco"] for la in lote_brincos]
        ca = None
        if brincos and consumo_real_total > 0:
            pes = supabase.table("pesagens").select("ganho_kg").gte("data", p["data_inicio"]).execute().data
            ganho_total = sum(pe["ganho_kg"] for pe in pes if pe.get("ganho_kg") and pe["ganho_kg"] > 0)
            if ganho_total > 0:
                ca = round(consumo_real_total / ganho_total, 2)

        saldo   = _saldo_estoque(p["suplemento_id"], fid if fid > 0 else None)
        cmd_dia = _consumo_medio_diario(p["suplemento_id"])
        dias_est, sit_est = _status_estoque(saldo, cmd_dia)

        result.append({
            **p,
            "lote_nome":       lote_rows[0]["nome"] if lote_rows else "—",
            "suplemento_nome": sup_rows[0]["nome"]  if sup_rows  else "—",
            "suplemento_tipo": sup_rows[0]["tipo"]  if sup_rows  else "—",
            "consumo_real_total_kg":  consumo_real_total,
            "consumo_plan_total_kg":  consumo_plan_total,
            "custo_real_total":       custo_real_total,
            "consumo_hoje_kg":        consumo_hoje,
            "consumo_med_lote_dia_kg": round(consumo_med_lote_dia, 3),
            "ca": ca,
            "ca_classificacao": _ca_classificacao(ca),
            "estoque_saldo_kg":  saldo,
            "estoque_dias":      dias_est,
            "estoque_situacao":  sit_est,
            "dias_em_vigor":     max(0, dias_plano),
        })
    return result


@router.post("/planos", status_code=201)
def criar_plano(request: Request, body: dict):
    fid = get_fazenda_id(request)
    lote_id = body.get("lote_id")
    sup_id  = body.get("suplemento_id")
    if not lote_id or not sup_id:
        raise HTTPException(400, "lote_id e suplemento_id são obrigatórios")

    lote_rows = supabase.table("lotes").select("*").eq("id", lote_id).limit(1).execute().data
    if not lote_rows:
        raise HTTPException(404, "Lote não encontrado")
    sup_rows = supabase.table("suplementos").select("*").eq("id", sup_id).limit(1).execute().data
    if not sup_rows:
        raise HTTPException(404, "Suplemento não encontrado")
    sup = sup_rows[0]

    existing = supabase.table("plano_nutricional").select("id").eq("lote_id", lote_id).eq("suplemento_id", sup_id).eq("status", "ATIVO").limit(1).execute().data
    if existing:
        raise HTTPException(400, "Já existe plano ATIVO com este suplemento para este lote")

    qtd_animais   = body.get("qtd_animais") or 1
    peso_medio_kg = body.get("peso_medio_kg") or 0.0
    g_min, g_max, g_med = _calc_consumo(sup, float(peso_medio_kg), int(qtd_animais))
    custo_dia, custo_mes = _custo_estimado(g_med, int(qtd_animais), sup["preco_kg"])

    data_inicio = body.get("data_inicio") or date.today().isoformat()
    row = {
        "lote_id":       lote_id,
        "suplemento_id": sup_id,
        "data_inicio":   data_inicio,
        "data_fim":      body.get("data_fim"),
        "qtd_animais":   int(qtd_animais),
        "peso_medio_kg": float(peso_medio_kg),
        "preco_kg_snap": sup["preco_kg"],
        "consumo_min_g": g_min,
        "consumo_max_g": g_max,
        "consumo_med_g": g_med,
        "custo_dia_est": custo_dia,
        "custo_mes_est": custo_mes,
        "status":        "ATIVO",
        "obs":           body.get("obs"),
        "fazenda_id":    fid if fid > 0 else 1,
    }
    result = supabase.table("plano_nutricional").insert(row).execute().data[0]
    return {"id": result["id"], "ok": True}


@router.put("/planos/{pid}")
def atualizar_plano(pid: int, body: dict):
    rows = supabase.table("plano_nutricional").select("*").eq("id", pid).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Plano não encontrado")
    update = {}
    if "status" in body:
        update["status"] = body["status"]
        if body["status"] == "ENCERRADO":
            update["data_fim"] = date.today().isoformat()
    if "obs" in body:
        update["obs"] = body["obs"]
    if "data_fim" in body:
        update["data_fim"] = body["data_fim"]
    supabase.table("plano_nutricional").update(update).eq("id", pid).execute()
    return {"ok": True}


@router.delete("/planos/{pid}")
def excluir_plano(pid: int):
    rows = supabase.table("plano_nutricional").select("id").eq("id", pid).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Plano não encontrado")
    lancs = supabase.table("lancamento_racao").select("id").eq("plano_id", pid).limit(1).execute().data
    if lancs:
        raise HTTPException(400, "Não é possível excluir: plano tem lançamentos registrados")
    supabase.table("plano_nutricional").delete().eq("id", pid).execute()
    return {"ok": True}


# ── LANÇAMENTOS DE RAÇÃO ──────────────────────────────────────────────────────

@router.get("/lancamentos")
def listar_lancamentos(
    request: Request,
    lote_id: Optional[int] = None,
    plano_id: Optional[int] = None,
    data_ini: Optional[str] = None,
    data_fim: Optional[str] = None,
):
    fid = get_fazenda_id(request)
    q = supabase.table("lancamento_racao").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    if lote_id:
        q = q.eq("lote_id", lote_id)
    if plano_id:
        q = q.eq("plano_id", plano_id)
    if data_ini:
        q = q.gte("data", data_ini)
    if data_fim:
        q = q.lte("data", data_fim)
    rows = q.order("data", desc=True).execute().data
    result = []
    for r in rows:
        sup_rows  = supabase.table("suplementos").select("nome").eq("id", r["suplemento_id"]).limit(1).execute().data
        lote_rows = supabase.table("lotes").select("nome").eq("id", r["lote_id"]).limit(1).execute().data
        result.append({
            **r,
            "lote_nome":       lote_rows[0]["nome"] if lote_rows else "—",
            "suplemento_nome": sup_rows[0]["nome"]  if sup_rows  else "—",
        })
    return result


@router.post("/lancamentos", status_code=201)
def criar_lancamento(request: Request, body: dict):
    fid = get_fazenda_id(request)
    plano_id = body.get("plano_id")
    if not plano_id:
        raise HTTPException(400, "plano_id é obrigatório")

    plano_rows = supabase.table("plano_nutricional").select("*").eq("id", plano_id).limit(1).execute().data
    if not plano_rows:
        raise HTTPException(404, "Plano não encontrado")
    plano = plano_rows[0]
    if plano["status"] != "ATIVO":
        raise HTTPException(400, "Plano não está ATIVO")

    data_lanc = body.get("data") or date.today().isoformat()
    if data_lanc > date.today().isoformat():
        raise HTTPException(400, "Data não pode ser futura")

    qtd_fornecida = float(body.get("qtd_fornecida_kg", 0))
    if qtd_fornecida <= 0:
        raise HTTPException(400, "qtd_fornecida_kg deve ser > 0")

    consumo_med_lote = (plano.get("consumo_med_g") or 0) / 1000 * (plano.get("qtd_animais") or 0)
    qtd_planejada = body.get("qtd_planejada_kg") or round(consumo_med_lote, 3)
    diferenca = round(qtd_fornecida - qtd_planejada, 3)
    preco_snap = plano.get("preco_kg_snap") or 0.0
    custo_real = round(qtd_fornecida * preco_snap, 2) if preco_snap else None

    row = {
        "plano_id":         plano_id,
        "lote_id":          plano["lote_id"],
        "suplemento_id":    plano["suplemento_id"],
        "data":             data_lanc,
        "qtd_fornecida_kg": qtd_fornecida,
        "qtd_planejada_kg": round(qtd_planejada, 3),
        "diferenca_kg":     diferenca,
        "custo_real":       custo_real,
        "responsavel":      body.get("responsavel"),
        "obs":              body.get("obs"),
        "fazenda_id":       fid if fid > 0 else (plano.get("fazenda_id") or 1),
    }
    result = supabase.table("lancamento_racao").insert(row).execute().data[0]

    # Debitar estoque automaticamente
    supabase.table("estoque_suplemento").insert({
        "suplemento_id": plano["suplemento_id"],
        "data":          data_lanc,
        "tipo_mov":      "SAIDA",
        "quantidade_kg": qtd_fornecida,
        "preco_kg":      preco_snap or None,
        "valor_total":   custo_real,
        "obs":           f"Automático – lançamento #{result['id']}",
        "fazenda_id":    fid if fid > 0 else 1,
    }).execute()

    return {"id": result["id"], "ok": True,
            "qtd_planejada_kg": round(qtd_planejada, 3),
            "diferenca_kg": diferenca,
            "custo_real": custo_real}


@router.put("/lancamentos/{lid}")
def atualizar_lancamento(lid: int, body: dict):
    rows = supabase.table("lancamento_racao").select("*").eq("id", lid).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lançamento não encontrado")
    old = rows[0]
    nova_qtd = float(body.get("qtd_fornecida_kg", old["qtd_fornecida_kg"]))
    diferenca_qtd = nova_qtd - old["qtd_fornecida_kg"]
    preco_snap = old.get("custo_real") / old["qtd_fornecida_kg"] if old.get("custo_real") and old["qtd_fornecida_kg"] else 0.0
    custo_real = round(nova_qtd * preco_snap, 2) if preco_snap else None
    qtd_plan   = old.get("qtd_planejada_kg") or 0
    update = {
        "qtd_fornecida_kg": nova_qtd,
        "diferenca_kg":     round(nova_qtd - qtd_plan, 3),
        "custo_real":       custo_real,
    }
    if "obs" in body:
        update["obs"] = body["obs"]
    supabase.table("lancamento_racao").update(update).eq("id", lid).execute()
    # Ajustar estoque pela diferença
    if abs(diferenca_qtd) > 0.001:
        tipo_mov = "SAIDA" if diferenca_qtd > 0 else "AJUSTE"
        qtd_mov  = abs(diferenca_qtd)
        supabase.table("estoque_suplemento").insert({
            "suplemento_id": old["suplemento_id"],
            "data":          old["data"],
            "tipo_mov":      tipo_mov,
            "quantidade_kg": round(qtd_mov, 3),
            "obs":           f"Ajuste correção lançamento #{lid}",
        }).execute()
    return {"ok": True}


@router.delete("/lancamentos/{lid}")
def excluir_lancamento(lid: int):
    rows = supabase.table("lancamento_racao").select("*").eq("id", lid).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Lançamento não encontrado")
    old = rows[0]
    supabase.table("lancamento_racao").delete().eq("id", lid).execute()
    # Devolver ao estoque
    supabase.table("estoque_suplemento").insert({
        "suplemento_id": old["suplemento_id"],
        "data":          old["data"],
        "tipo_mov":      "AJUSTE",
        "quantidade_kg": old["qtd_fornecida_kg"],
        "obs":           f"Devolução exclusão lançamento #{lid}",
    }).execute()
    return {"ok": True}


# ── ESTOQUE ───────────────────────────────────────────────────────────────────

@router.get("/estoque")
def listar_estoque(request: Request):
    fid = get_fazenda_id(request)
    suplementos = supabase.table("suplementos").select("*").eq("ativo", True).order("nome").execute().data
    result = []
    for s in suplementos:
        saldo = _saldo_estoque(s["id"], fid if fid > 0 else None)
        cmd   = _consumo_medio_diario(s["id"])
        dias, sit = _status_estoque(saldo, cmd)
        result.append({
            "suplemento_id": s["id"], "nome": s["nome"], "tipo": s["tipo"],
            "saldo_kg":              saldo,
            "preco_kg":              s["preco_kg"],
            "valor_estoque":         round(saldo * s["preco_kg"], 2),
            "consumo_medio_dia_kg":  cmd,
            "dias_restantes":        dias,
            "situacao":              sit,
        })
    return result


@router.get("/estoque/historico/{suplemento_id}")
def historico_estoque(suplemento_id: int, tipo_mov: Optional[str] = None,
                      data_ini: Optional[str] = None, data_fim: Optional[str] = None):
    q = supabase.table("estoque_suplemento").select("*").eq("suplemento_id", suplemento_id)
    if tipo_mov:
        q = q.eq("tipo_mov", tipo_mov)
    if data_ini:
        q = q.gte("data", data_ini)
    if data_fim:
        q = q.lte("data", data_fim)
    rows = q.order("data", desc=False).execute().data
    saldo_acum = 0.0
    result = []
    for r in rows:
        if r["tipo_mov"] in ("ENTRADA", "AJUSTE"):
            saldo_acum += r["quantidade_kg"]
        else:
            saldo_acum -= r["quantidade_kg"]
        result.insert(0, {**r, "saldo_acumulado": round(saldo_acum, 3)})
    return result


@router.post("/estoque/entrada", status_code=201)
def entrada_estoque(request: Request, body: dict):
    fid = get_fazenda_id(request)
    sup_id = body.get("suplemento_id")
    if not sup_id:
        raise HTTPException(400, "suplemento_id obrigatório")
    qtd    = float(body.get("quantidade_kg", 0))
    preco  = body.get("preco_kg")
    if qtd <= 0:
        raise HTTPException(400, "quantidade_kg deve ser > 0")
    valor = round(qtd * float(preco), 2) if preco else None
    row = {
        "suplemento_id": sup_id,
        "data":          body.get("data") or date.today().isoformat(),
        "tipo_mov":      "ENTRADA",
        "quantidade_kg": qtd,
        "preco_kg":      preco,
        "valor_total":   valor,
        "fornecedor":    body.get("fornecedor"),
        "nf":            body.get("nf"),
        "obs":           body.get("obs"),
        "fazenda_id":    fid if fid > 0 else 1,
    }
    result = supabase.table("estoque_suplemento").insert(row).execute().data[0]
    # Atualizar preço do suplemento
    if preco:
        supabase.table("suplementos").update({"preco_kg": float(preco)}).eq("id", sup_id).execute()
    return {"id": result["id"], "ok": True}


@router.post("/estoque/ajuste", status_code=201)
def ajuste_estoque(request: Request, body: dict):
    fid = get_fazenda_id(request)
    sup_id = body.get("suplemento_id")
    if not sup_id:
        raise HTTPException(400, "suplemento_id obrigatório")
    qtd = float(body.get("quantidade_kg", 0))
    row = {
        "suplemento_id": sup_id,
        "data":          body.get("data") or date.today().isoformat(),
        "tipo_mov":      "AJUSTE",
        "quantidade_kg": qtd,
        "obs":           body.get("obs"),
        "fazenda_id":    fid if fid > 0 else 1,
    }
    result = supabase.table("estoque_suplemento").insert(row).execute().data[0]
    return {"id": result["id"], "ok": True}


@router.post("/estoque/movimento", status_code=201)
def registrar_movimento(request: Request, body: dict):
    fid = get_fazenda_id(request)
    allowed = {"suplemento_id", "data", "tipo_mov", "quantidade_kg",
               "preco_kg", "valor_total", "fornecedor", "nf", "obs"}
    data = {k: v for k, v in body.items() if k in allowed}
    if data.get("preco_kg") and data.get("quantidade_kg"):
        data["valor_total"] = round(float(data["quantidade_kg"]) * float(data["preco_kg"]), 2)
    data["fazenda_id"] = fid if fid > 0 else 1
    result = supabase.table("estoque_suplemento").insert(data).execute().data[0]
    return {"id": result["id"], "ok": True}


# ── RELATÓRIOS ────────────────────────────────────────────────────────────────

@router.get("/relatorio/dashboard")
def relatorio_dashboard(request: Request):
    fid = get_fazenda_id(request)
    hoje = date.today().isoformat()

    planos_q = supabase.table("plano_nutricional").select("*").eq("status", "ATIVO")
    if fid > 0:
        planos_q = planos_q.eq("fazenda_id", fid)
    planos = planos_q.execute().data

    custo_dia_total = 0.0
    for p in planos:
        custo_dia_total += p.get("custo_dia_est") or 0

    # Consumo real vs planejado hoje
    lancs_hoje_q = supabase.table("lancamento_racao").select("qtd_fornecida_kg,qtd_planejada_kg").eq("data", hoje)
    if fid > 0:
        lancs_hoje_q = lancs_hoje_q.eq("fazenda_id", fid)
    lancs_hoje = lancs_hoje_q.execute().data
    real_hoje = sum(l["qtd_fornecida_kg"] for l in lancs_hoje)
    plan_hoje = sum((l.get("qtd_planejada_kg") or 0) for l in lancs_hoje)
    consumo_pct = round(real_hoje / plan_hoje * 100, 1) if plan_hoje > 0 else None

    # Estoque crítico e baixo
    critico, baixo = [], []
    sups = supabase.table("suplementos").select("id,nome").eq("ativo", True).execute().data
    for s in sups:
        saldo = _saldo_estoque(s["id"], fid if fid > 0 else None)
        cmd   = _consumo_medio_diario(s["id"])
        dias, sit = _status_estoque(saldo, cmd)
        if sit == "CRITICO":
            critico.append(s["nome"])
        elif sit == "BAIXO":
            baixo.append(s["nome"])

    return {
        "lotes_com_plano":             len(planos),
        "custo_dia_total":             round(custo_dia_total, 2),
        "custo_mes_estimado":          round(custo_dia_total * 30, 2),
        "estoque_critico":             critico,
        "estoque_baixo":               baixo,
        "consumo_real_vs_planejado_pct": consumo_pct,
    }


@router.get("/relatorio/custo-lote")
def custo_por_lote(request: Request,
                   lote_id: int = Query(...),
                   periodo_dias: int = Query(30)):
    fid = get_fazenda_id(request)
    data_ini = (date.today() - timedelta(days=periodo_dias)).isoformat()
    hoje = date.today().isoformat()
    q = supabase.table("lancamento_racao").select("*").eq("lote_id", lote_id).gte("data", data_ini)
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    lancs = q.execute().data
    if not lancs:
        return {"lote_id": lote_id, "periodo_dias": periodo_dias, "total_consumido_kg": 0}

    total_consumido = round(sum(l["qtd_fornecida_kg"] for l in lancs), 3)
    custo_total     = round(sum((l.get("custo_real") or 0) for l in lancs), 2)

    # Pesagens no período
    lote_brincos = supabase.table("lote_animais").select("brinco").eq("lote_id", lote_id).execute().data
    brincos = [la["brinco"] for la in lote_brincos]
    ganho_total = 0.0
    if brincos:
        pes = supabase.table("pesagens").select("ganho_kg").gte("data", data_ini).execute().data
        ganho_total = sum(p["ganho_kg"] for p in pes if p.get("ganho_kg") and p["ganho_kg"] > 0)

    ca = round(total_consumido / ganho_total, 2) if ganho_total > 0 else None
    arrobas = round(ganho_total / 15, 2) if ganho_total else None
    custo_arroba = round(custo_total / arrobas, 2) if arrobas and arrobas > 0 else None
    custo_kg_ganho = round(custo_total / ganho_total, 2) if ganho_total > 0 else None

    # Plano ativo
    plan_rows = supabase.table("plano_nutricional").select("qtd_animais").eq("lote_id", lote_id).eq("status", "ATIVO").limit(1).execute().data
    qtd_animais = plan_rows[0]["qtd_animais"] if plan_rows else None
    dias_efetivos = len(set(l["data"] for l in lancs))
    custo_cab_dia = round(custo_total / (qtd_animais * dias_efetivos), 4) if qtd_animais and dias_efetivos else None

    # Por suplemento
    por_sup: dict = {}
    for l in lancs:
        sid = l["suplemento_id"]
        por_sup.setdefault(sid, {"consumido_kg": 0, "custo": 0})
        por_sup[sid]["consumido_kg"] += l["qtd_fornecida_kg"]
        por_sup[sid]["custo"] += l.get("custo_real") or 0
    sup_detail = []
    for sid, vals in por_sup.items():
        sup_rows = supabase.table("suplementos").select("nome").eq("id", sid).limit(1).execute().data
        sup_detail.append({"nome": sup_rows[0]["nome"] if sup_rows else str(sid),
                           "consumido_kg": round(vals["consumido_kg"], 3),
                           "custo": round(vals["custo"], 2)})

    return {
        "lote_id":            lote_id,
        "periodo_dias":       periodo_dias,
        "total_consumido_kg": total_consumido,
        "custo_total":        custo_total,
        "custo_cab_dia":      custo_cab_dia,
        "custo_arroba":       custo_arroba,
        "custo_kg_ganho":     custo_kg_ganho,
        "ganho_total_kg":     round(ganho_total, 3),
        "arrobas_produzidas": arrobas,
        "ca":                 ca,
        "ca_classificacao":   _ca_classificacao(ca),
        "por_suplemento":     sup_detail,
    }


@router.get("/relatorios/ca")
def relatorio_ca(
    lote_id: Optional[int] = None,
    data_ini: Optional[str] = None,
    data_fim: Optional[str] = None,
):
    if not data_ini:
        data_ini = (date.today() - timedelta(days=90)).isoformat()
    if not data_fim:
        data_fim = date.today().isoformat()
    q = supabase.table("lancamento_racao").select("*").gte("data", data_ini).lte("data", data_fim)
    if lote_id:
        q = q.eq("lote_id", lote_id)
    lancamentos = q.execute().data
    lotes_ids = list(set(l["lote_id"] for l in lancamentos))
    result = []
    for lid in lotes_ids:
        lote_rows = supabase.table("lotes").select("nome").eq("id", lid).limit(1).execute().data
        lote_brincos = supabase.table("lote_animais").select("brinco").eq("lote_id", lid).execute().data
        brincos = [la["brinco"] for la in lote_brincos]
        consumo_total_kg = sum(l["qtd_fornecida_kg"] for l in lancamentos if l["lote_id"] == lid)
        ganho_total_kg = None
        if brincos:
            pes = supabase.table("pesagens").select("ganho_kg").gte("data", data_ini).lte("data", data_fim).execute().data
            g = sum(p["ganho_kg"] for p in pes if p.get("ganho_kg") and p["ganho_kg"] > 0)
            if g > 0:
                ganho_total_kg = g
        ca = round(consumo_total_kg / ganho_total_kg, 2) if ganho_total_kg else None
        result.append({
            "lote_id": lid,
            "lote_nome": lote_rows[0]["nome"] if lote_rows else "—",
            "consumo_total_kg": round(consumo_total_kg, 2),
            "ganho_total_kg": round(ganho_total_kg, 2) if ganho_total_kg else None,
            "ca": ca,
            "ca_classificacao": _ca_classificacao(ca),
        })
    return result


@router.get("/relatorios/custo-mensal")
def custo_mensal():
    data_ini = (date.today() - timedelta(days=365)).isoformat()
    rows = supabase.table("lancamento_racao").select("data,custo_real").gte("data", data_ini).execute().data
    mensal: dict = {}
    for r in rows:
        mes = r["data"][:7]
        mensal[mes] = mensal.get(mes, 0) + (r.get("custo_real") or 0)
    return [{"mes": k, "custo": round(v, 2)} for k, v in sorted(mensal.items())]


@router.get("/relatorios/resumo")
def resumo_nutricao():
    hoje = date.today().isoformat()
    mes_ini = hoje[:7] + "-01"
    planos = supabase.table("plano_nutricional").select("id,custo_dia_est").eq("status", "ATIVO").execute().data
    planos_ativos = len(planos)
    custo_dia_total = sum((p.get("custo_dia_est") or 0) for p in planos)
    lancs = supabase.table("lancamento_racao").select("custo_real").gte("data", mes_ini).execute().data
    custo_mes = sum(r.get("custo_real") or 0 for r in lancs)
    suplementos = supabase.table("suplementos").select("*").eq("ativo", True).execute().data
    criticos = 0
    for s in suplementos:
        saldo = _saldo_estoque(s["id"])
        cmd = _consumo_medio_diario(s["id"])
        _, sit = _status_estoque(saldo, cmd)
        if sit == "CRITICO":
            criticos += 1
    return {
        "planos_ativos":   planos_ativos,
        "custo_dia_total": round(custo_dia_total, 2),
        "custo_mes":       round(custo_mes, 2),
        "estoque_critico": criticos,
        "total_suplementos": len(suplementos),
    }


# ── SEED ─────────────────────────────────────────────────────────────────────

def seed_nutricao(db=None):
    rows = supabase.table("suplementos").select("id,tipo").limit(10).execute().data
    tipos_existentes = {r.get("tipo") for r in rows}
    # Só re-seed se os tipos padrão novos não existirem
    if "SAL_MINERAL" in tipos_existentes:
        return

    suplementos_base = [
        {"nome": "Sal Mineral Padrão",    "tipo": "SAL_MINERAL",       "preco_kg": 2.50,
         "g_min_fixo": 80, "g_max_fixo": 100, "objetivo": "Mantença e Recria", "ativo": True},
        {"nome": "Sal Proteinado 30%",    "tipo": "SAL_PROTEINADO",    "preco_kg": 3.80,
         "pct_min": 0.001, "pct_max": 0.003, "objetivo": "Período de Seca e Transição", "ativo": True},
        {"nome": "Prot. Energético 40%",  "tipo": "PROT_ENERGETICO",   "preco_kg": 4.50,
         "pct_min": 0.003, "pct_max": 0.005, "objetivo": "Recria e Engorda", "ativo": True},
        {"nome": "Ração Terminação",      "tipo": "RACAO_SEMICONFINADO", "preco_kg": 1.90,
         "pct_min": 0.007, "pct_max": 0.015, "objetivo": "Terminação e Semiconfinamento", "ativo": True},
        {"nome": "Silagem de Milho",      "tipo": "VOLUMOSO_SILAGEM",  "preco_kg": 0.35,
         "pct_min": 0.020, "pct_max": 0.030, "objetivo": "Mantença e Engorda em confinamento", "ativo": True},
    ]

    # Remover suplementos com tipos antigos se existirem
    for r in rows:
        if r.get("tipo") in ("MINERAL", "PROTEICO", "ENERGETICO", "PROTEINADO", "OUTRO"):
            try:
                supabase.table("suplementos").delete().eq("id", r["id"]).execute()
            except Exception:
                pass

    for s in suplementos_base:
        existing = supabase.table("suplementos").select("id").ilike("nome", s["nome"]).limit(1).execute().data
        if not existing:
            supabase.table("suplementos").insert(s).execute()

    # Seed plano para lote "Vacas Pasto Norte"
    try:
        lote_rows = supabase.table("lotes").select("id").ilike("nome", "%Vacas Pasto Norte%").limit(1).execute().data
        if not lote_rows:
            return
        lote_id = lote_rows[0]["id"]

        sup_rows = supabase.table("suplementos").select("id,preco_kg").eq("tipo", "SAL_PROTEINADO").limit(1).execute().data
        if not sup_rows:
            return
        sup = sup_rows[0]
        sup_id = sup["id"]

        plano_exist = supabase.table("plano_nutricional").select("id").eq("lote_id", lote_id).eq("suplemento_id", sup_id).limit(1).execute().data
        if not plano_exist:
            data_inicio = (date.today() - timedelta(days=30)).isoformat()
            qtd_animais, peso_medio_kg = 20, 380.0
            g_min, g_max, g_med = _calc_consumo(sup_rows[0], peso_medio_kg, qtd_animais)
            # Need full sup data
            sup_full = supabase.table("suplementos").select("*").eq("id", sup_id).limit(1).execute().data[0]
            g_min, g_max, g_med = _calc_consumo(sup_full, peso_medio_kg, qtd_animais)
            custo_dia = round(g_med / 1000 * qtd_animais * sup_full["preco_kg"], 2)
            plano_data = {
                "lote_id": lote_id, "suplemento_id": sup_id,
                "data_inicio": data_inicio, "data_fim": None,
                "qtd_animais": qtd_animais, "peso_medio_kg": peso_medio_kg,
                "preco_kg_snap": sup_full["preco_kg"],
                "consumo_min_g": g_min, "consumo_max_g": g_max, "consumo_med_g": g_med,
                "custo_dia_est": custo_dia, "custo_mes_est": round(custo_dia * 30, 2),
                "status": "ATIVO", "fazenda_id": 1,
            }
            plano_rows = supabase.table("plano_nutricional").insert(plano_data).execute().data
            plano_id = plano_rows[0]["id"]

            # 10 lançamentos diários
            for i in range(10, 0, -1):
                dt = (date.today() - timedelta(days=i)).isoformat()
                qtd_plan = round(g_med / 1000 * qtd_animais, 3)
                qtd_real = round(qtd_plan * 0.92, 3)  # 92% do planejado
                custo_real = round(qtd_real * sup_full["preco_kg"], 2)
                lanc_exist = supabase.table("lancamento_racao").select("id").eq("plano_id", plano_id).eq("data", dt).limit(1).execute().data
                if not lanc_exist:
                    supabase.table("lancamento_racao").insert({
                        "plano_id": plano_id, "lote_id": lote_id, "suplemento_id": sup_id,
                        "data": dt, "qtd_fornecida_kg": qtd_real, "qtd_planejada_kg": qtd_plan,
                        "diferenca_kg": round(qtd_real - qtd_plan, 3),
                        "custo_real": custo_real, "fazenda_id": 1,
                    }).execute()

        # Seed estoque
        est_exist = supabase.table("estoque_suplemento").select("id").eq("suplemento_id", sup_id).eq("tipo_mov", "ENTRADA").limit(1).execute().data
        if not est_exist:
            dt_entrada = (date.today() - timedelta(days=30)).isoformat()
            supabase.table("estoque_suplemento").insert({
                "suplemento_id": sup_id, "data": dt_entrada, "tipo_mov": "ENTRADA",
                "quantidade_kg": 200, "preco_kg": 3.80, "valor_total": 760,
                "fornecedor": "Agropecuária Central", "fazenda_id": 1,
            }).execute()

        # Prot. Energético estoque
        pe_rows = supabase.table("suplementos").select("id").eq("tipo", "PROT_ENERGETICO").limit(1).execute().data
        if pe_rows:
            pe_id = pe_rows[0]["id"]
            est_pe = supabase.table("estoque_suplemento").select("id").eq("suplemento_id", pe_id).eq("tipo_mov", "ENTRADA").limit(1).execute().data
            if not est_pe:
                dt_pe = (date.today() - timedelta(days=15)).isoformat()
                supabase.table("estoque_suplemento").insert({
                    "suplemento_id": pe_id, "data": dt_pe, "tipo_mov": "ENTRADA",
                    "quantidade_kg": 150, "preco_kg": 4.50, "valor_total": 675,
                    "fornecedor": "Nutripec", "fazenda_id": 1,
                }).execute()
    except Exception:
        pass
