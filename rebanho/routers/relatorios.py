from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Query, Request

from database import supabase, get_fazenda_id

router = APIRouter()

_TIPOS = ["VACA", "TOURO", "BOI", "GARROTE", "NOVILHA", "BEZERRO", "BEZERRA"]


def _calcular_gmd(brinco: str, dias_janela: int, db=None, fazenda_id: Optional[int] = None):
    q = supabase.table("pesagens").select("peso_kg,ganho_kg,data").ilike("brinco", brinco)
    if fazenda_id:
        q = q.eq("fazenda_id", fazenda_id)
    pesagens_all = q.order("data").execute().data
    if dias_janela > 0:
        cutoff = (date.today() - timedelta(days=dias_janela)).isoformat()
        pesagens = [p for p in pesagens_all if (p.get("data") or "") >= cutoff]
    else:
        pesagens = []
    if len(pesagens) < 2:
        pesagens = pesagens_all
    if len(pesagens) < 2:
        return None, len(pesagens)
    total_ganho = sum(p.get("ganho_kg") or 0 for p in pesagens)
    try:
        d_ini = date.fromisoformat(pesagens[0]["data"])
        d_fim = date.fromisoformat(pesagens[-1]["data"])
        dias = (d_fim - d_ini).days
    except Exception:
        dias = 0
    if dias <= 0:
        return None, len(pesagens)
    return round(total_ganho / dias, 4), len(pesagens)


def _previsao_animal(animal: dict, peso_alvo: float, dias_gmd: int, preco_arroba: Optional[float], db=None) -> dict:
    hoje = date.today()
    peso_atual = animal.get("peso_atual") or 0
    fid = animal.get("fazenda_id")
    gmd, qtd_pes = _calcular_gmd(animal["brinco"], dias_gmd, fazenda_id=fid)
    arrobas = round(peso_alvo / 15, 2)

    if peso_atual >= peso_alvo:
        situacao = "PRONTO"; semaforo = "VERDE"
        dias_rest = 0; data_prev = data_otim = data_pess = hoje.isoformat()
    elif gmd is None:
        situacao = "SEM_DADOS"; semaforo = "CINZA"
        dias_rest = None; data_prev = data_otim = data_pess = None
    elif gmd <= 0:
        situacao = "GMD_INVALIDO"; semaforo = "CINZA"
        dias_rest = None; data_prev = data_otim = data_pess = None
    else:
        diferenca = peso_alvo - peso_atual
        dias_rest = round(diferenca / gmd)
        if dias_rest > 180:
            situacao = "LONGO_PRAZO"; semaforo = "CINZA"
        elif dias_rest > 90:
            situacao = "MEDIO_PRAZO"; semaforo = "AMARELO"
        else:
            situacao = "NO_PRAZO"; semaforo = "VERDE"
        data_prev = (hoje + timedelta(days=dias_rest)).isoformat()
        data_otim = (hoje + timedelta(days=round(diferenca / (gmd * 1.15)))).isoformat()
        data_pess = (hoje + timedelta(days=round(diferenca / (gmd * 0.85)))).isoformat()

    receita = lucro = None
    if preco_arroba and situacao not in ("SEM_DADOS", "GMD_INVALIDO"):
        receita = round(arrobas * preco_arroba, 2)
        if animal.get("valor_compra"):
            lucro = round(receita - animal["valor_compra"], 2)

    return {
        "brinco": animal["brinco"],
        "nome": animal.get("nome"),
        "tipo": animal.get("tipo"),
        "raca": animal.get("raca"),
        "pasto": animal.get("pasto_atual"),
        "lote": None,
        "peso_atual": peso_atual,
        "peso_alvo": peso_alvo,
        "diferenca_kg": round(max(0, peso_alvo - peso_atual), 2),
        "gmd_real": gmd,
        "gmd_periodo_dias": dias_gmd,
        "qtd_pesagens": qtd_pes,
        "dias_restantes": dias_rest,
        "data_prevista": data_prev,
        "data_otimista": data_otim,
        "data_pessimista": data_pess,
        "arrobas_previstas": arrobas,
        "receita_estimada": receita,
        "lucro_estimado": lucro,
        "valor_compra": animal.get("valor_compra"),
        "situacao": situacao,
        "semaforo": semaforo,
    }


@router.get("/kpis")
def kpis(request: Request):
    hoje = date.today()
    hoje_iso = hoje.isoformat()
    hoje_str = hoje.strftime("%Y-%m")
    fid = get_fazenda_id(request)
    if fid <= 0:
        fid = None

    # Rebanho
    q_animais = supabase.table("animais").select("id,tipo,status,valor_compra,custo_kg,custo_arroba,brinco,fazenda_id")
    if fid:
        q_animais = q_animais.eq("fazenda_id", fid)
    animais_all = q_animais.execute().data
    total_por_tipo = {t: 0 for t in _TIPOS}
    for a in animais_all:
        if (a.get("status") or "").upper() == "ATIVO" and a.get("tipo") in total_por_tipo:
            total_por_tipo[a["tipo"]] += 1
    total_ativo = sum(total_por_tipo.values())
    rebanho = {"total_ativo": total_ativo, "total_por_tipo": total_por_tipo}

    # Financeiro rebanho
    ativos_com_compra = [a for a in animais_all if (a.get("status") or "").upper() == "ATIVO" and (a.get("valor_compra") or 0) > 0]
    valor_total = sum(a.get("valor_compra") or 0 for a in ativos_com_compra)
    custos_kg  = [a["custo_kg"]     for a in ativos_com_compra if a.get("custo_kg")]
    custos_arr = [a["custo_arroba"] for a in ativos_com_compra if a.get("custo_arroba")]
    mais_caro  = max(ativos_com_compra, key=lambda a: a.get("valor_compra") or 0) if ativos_com_compra else None
    financeiro_rebanho = {
        "valor_total_compras_animais": round(valor_total, 2),
        "custo_medio_kg":     round(sum(custos_kg)/len(custos_kg), 2)   if custos_kg  else None,
        "custo_medio_arroba": round(sum(custos_arr)/len(custos_arr), 2) if custos_arr else None,
        "animal_mais_caro": {"brinco": mais_caro["brinco"], "nome": mais_caro.get("nome"),
                             "valor_compra": mais_caro["valor_compra"]} if mais_caro else None,
    }

    # Config
    cfg_rows = supabase.table("config").select("*").execute().data
    cfg = {r["chave"]: r["valor"] for r in cfg_rows}
    peso_alvo_padrao = float(cfg.get("peso_alvo_padrao", "480"))
    preco_arr_padrao = float(cfg.get("preco_arroba_padrao", "0") or "0")

    # Previsão de saída
    q_ativos = supabase.table("animais").select("*")
    if fid:
        q_ativos = q_ativos.eq("fazenda_id", fid)
    animais_ativos = [a for a in q_ativos.execute().data if (a.get("status") or "").upper() == "ATIVO"]
    prev_results = [_previsao_animal(a, peso_alvo_padrao, 90, preco_arr_padrao if preco_arr_padrao else None, None)
                    for a in animais_ativos]
    prontos_prev = sum(1 for r in prev_results if r["situacao"] == "PRONTO")
    no_prazo_prev = sum(1 for r in prev_results if r["situacao"] == "NO_PRAZO")
    medio_prazo_prev = sum(1 for r in prev_results if r["situacao"] == "MEDIO_PRAZO")
    longo_prazo_prev = sum(1 for r in prev_results if r["situacao"] == "LONGO_PRAZO")
    sem_dados_prev = sum(1 for r in prev_results if r["situacao"] in ("SEM_DADOS", "GMD_INVALIDO"))
    animais_proximos = sorted([r for r in prev_results if r["data_prevista"]], key=lambda r: r["data_prevista"])[:5]
    previsao_saida = {
        "peso_alvo": peso_alvo_padrao,
        "prontos": prontos_prev, "no_prazo_90d": no_prazo_prev,
        "medio_prazo": medio_prazo_prev, "longo_prazo": longo_prazo_prev,
        "sem_dados": sem_dados_prev, "animais_proximos": [
            {k: r[k] for k in ("brinco","nome","tipo","peso_atual","peso_alvo","dias_restantes","situacao","semaforo","data_prevista","gmd_real")}
            for r in animais_proximos
        ],
    }

    # Pastagem
    q_chuvas = supabase.table("chuva").select("data,mm")
    if fid:
        q_chuvas = q_chuvas.eq("fazenda_id", fid)
    chuvas = q_chuvas.execute().data
    chuva_mes = round(sum(c["mm"] for c in chuvas if c.get("data") and c["data"][:7] == hoje_str and c.get("mm")), 1)

    from routers.pastagem import semaforo_piquete as _semaforo
    q_piquetes = supabase.table("piquetes").select("*")
    if fid:
        q_piquetes = q_piquetes.eq("fazenda_id", fid)
    piquetes = q_piquetes.execute().data
    sem_counts = {s: 0 for s in ("VERDE", "AMARELO", "VERMELHO", "SAIR_AGORA", "OCUPADO", "SEM_DADOS")}
    piquetes_lista = []
    for pq in piquetes:
        s_info = _semaforo(pq["id"], None)
        s = s_info["semaforo"]
        sem_counts[s] = sem_counts.get(s, 0) + 1
        piquetes_lista.append({"id": pq["id"], "nome": pq["nome"], "semaforo": s,
                                "area_ha": pq.get("area_ha"), "status": pq.get("semaforo")})
    pastagem_kpi = {
        "verde": sem_counts["VERDE"], "amarelo": sem_counts["AMARELO"],
        "vermelho": sem_counts["VERMELHO"], "sair_agora": sem_counts["SAIR_AGORA"],
        "ocupado": sem_counts["OCUPADO"], "sem_dados": sem_counts["SEM_DADOS"],
        "alerta_seca": chuva_mes < 50, "chuva_mes_mm": chuva_mes, "piquetes": piquetes_lista,
    }

    # Lotes
    q_lotes = supabase.table("lotes").select("*").ilike("status", "ATIVO")
    if fid:
        q_lotes = q_lotes.eq("fazenda_id", fid)
    lotes_ativos = q_lotes.execute().data
    lotes_lista = []
    for lt in lotes_ativos:
        q_la = supabase.table("lote_animais").select("id").eq("lote_id", lt["id"])
        if fid:
            q_la = q_la.eq("fazenda_id", fid)
        qtd = len(q_la.execute().data)
        lotes_lista.append({
            "id": lt["id"], "nome": lt["nome"], "categoria": lt.get("classificacao"),
            "qtd_animais": qtd, "ua_total": None, "ua_ha": lt.get("ua_ha"),
            "classificacao": lt.get("classificacao"),
        })
    lotes_kpi = {"total_ativos": len(lotes_ativos), "lista": lotes_lista}

    # Alertas
    alertas_geradas = []
    despesas_venc = supabase.table("despesas").select("*").ilike("status", "PENDENTE").lt("vencimento", hoje_iso).order("vencimento").execute().data
    for d in despesas_venc:
        alertas_geradas.append({
            "nivel": "CRITICO", "icone": "🔴",
            "msg": f"Despesa vencida: {d.get('categoria')} — {d.get('descricao')} ({d.get('vencimento')})",
            "valor": d.get("valor"),
        })
    limite_7d = (hoje + timedelta(days=7)).isoformat()
    despesas_prox = supabase.table("despesas").select("*").ilike("status", "PENDENTE").gte("vencimento", hoje_iso).lte("vencimento", limite_7d).execute().data
    for d in despesas_prox:
        alertas_geradas.append({
            "nivel": "ATENCAO", "icone": "🟡",
            "msg": f"Vence em 7 dias: {d.get('categoria')} — {d.get('descricao')} ({d.get('vencimento')})",
            "valor": d.get("valor"),
        })
    if sem_counts["SAIR_AGORA"] > 0:
        alertas_geradas.append({"nivel": "CRITICO", "icone": "🔴",
                                 "msg": f"{sem_counts['SAIR_AGORA']} piquete(s) precisam ser esvaziados agora", "valor": None})
    if chuva_mes < 30:
        alertas_geradas.append({"nivel": "CRITICO", "icone": "🔴",
                                 "msg": f"Seca crítica: apenas {chuva_mes} mm de chuva no mês", "valor": None})
    elif chuva_mes < 50:
        alertas_geradas.append({"nivel": "ATENCAO", "icone": "🟡",
                                 "msg": f"Chuva abaixo do ideal: {chuva_mes} mm no mês", "valor": None})
    if prontos_prev > 0:
        alertas_geradas.append({"nivel": "INFO", "icone": "🟢",
                                 "msg": f"{prontos_prev} animal(is) atingiu o peso alvo de {peso_alvo_padrao:.0f} kg", "valor": None})

    # Últimas pesagens
    q_ult = supabase.table("pesagens").select("brinco,data,peso_kg,ganho_kg")
    if fid:
        q_ult = q_ult.eq("fazenda_id", fid)
    ultimas = q_ult.order("data", desc=True).limit(5).execute().data
    pesagens_out = [{"brinco": p["brinco"], "data": p["data"], "peso": p.get("peso_kg"), "ganho_kg": p.get("ganho_kg")} for p in ultimas]

    alertas_despesas_out = [{"id": d["id"], "tipo": d.get("categoria"), "descricao": d.get("descricao"),
                              "valor": d.get("valor"), "vencimento": d.get("vencimento")} for d in despesas_venc]

    # Nutrição
    q_planos = supabase.table("plano_nutricional").select("id").eq("status", "ATIVO")
    if fid:
        q_planos = q_planos.eq("fazenda_id", fid)
    planos_ativos = len(q_planos.execute().data)
    mes_ini = hoje_str + "-01"
    q_custo = supabase.table("lancamento_racao").select("custo_real").gte("data", mes_ini)
    if fid:
        q_custo = q_custo.eq("fazenda_id", fid)
    custo_nut_mes = sum(r.get("custo_real") or 0 for r in q_custo.execute().data)
    sups_ativos = supabase.table("suplementos").select("*").eq("ativo", True).execute().data
    estoque_critico = 0
    from routers.nutricao import _saldo_estoque, _consumo_medio_diario
    for s in sups_ativos:
        saldo = _saldo_estoque(suplemento_id=s["id"], fazenda_id=fid)
        cmd = _consumo_medio_diario(suplemento_id=s["id"], fazenda_id=fid)
        if cmd and cmd > 0 and (saldo / cmd) < 7:
            estoque_critico += 1
    nutricao_kpi = {
        "planos_ativos": planos_ativos, "custo_mes": round(float(custo_nut_mes), 2),
        "estoque_critico": estoque_critico, "total_suplementos": len(sups_ativos),
    }

    # Confinamento
    q_lotes_conf = supabase.table("lotes_confinamento").select("*").eq("status", "ATIVO")
    if fid:
        q_lotes_conf = q_lotes_conf.eq("fazenda_id", fid)
    lotes_conf_ativos = q_lotes_conf.execute().data
    animais_conf = sum(l["qtd_animais"] for l in lotes_conf_ativos)
    custo_conf_rows = supabase.table("lancamento_confinamento").select("custo_real").gte("data", mes_ini).execute().data
    custo_conf_mes = sum(r.get("custo_real") or 0 for r in custo_conf_rows)
    gmds_conf = []; cas_conf = []; proxima_saida_conf = None
    for lc in lotes_conf_ativos:
        try:
            ult = supabase.table("pesagem_confinamento").select("peso_medio_kg").eq("lote_conf_id", lc["id"]).order("data", desc=True).limit(1).execute().data
            peso_at = ult[0]["peso_medio_kg"] if ult else lc["peso_medio_entrada"]
            dias_lc = max((hoje - date.fromisoformat(lc["data_entrada"])).days, 1)
            ganho = peso_at - lc["peso_medio_entrada"]
            gmd_lc = ganho / dias_lc
            if gmd_lc > 0:
                gmds_conf.append(gmd_lc)
                ms_rows = supabase.table("lancamento_confinamento").select("ms_fornecida_kg").eq("lote_conf_id", lc["id"]).execute().data
                total_ms = sum(r.get("ms_fornecida_kg") or 0 for r in ms_rows)
                ganho_total = ganho * lc["qtd_animais"]
                if ganho_total > 0:
                    cas_conf.append(total_ms / ganho_total)
                dias_rest = round((lc["peso_alvo_saida"] - peso_at) / gmd_lc)
                if dias_rest >= 0:
                    dt_saida = (hoje + timedelta(days=dias_rest)).isoformat()
                    if not proxima_saida_conf or dt_saida < proxima_saida_conf["data"]:
                        proxima_saida_conf = {"lote": lc["nome"], "data": dt_saida, "dias": dias_rest}
        except Exception:
            pass
    confinamento_kpi = {
        "lotes_ativos": len(lotes_conf_ativos), "animais_confinados": animais_conf,
        "custo_mes": round(float(custo_conf_mes), 2),
        "gmd_medio": round(sum(gmds_conf) / len(gmds_conf), 2) if gmds_conf else None,
        "ca_medio": round(sum(cas_conf) / len(cas_conf), 1) if cas_conf else None,
        "proxima_saida": proxima_saida_conf,
    }

    return {
        "rebanho": rebanho, "financeiro": financeiro_rebanho, "previsao_saida": previsao_saida,
        "pastagem": pastagem_kpi, "lotes": lotes_kpi, "alertas": alertas_geradas,
        "ultimas_pesagens": pesagens_out, "config": cfg, "nutricao": nutricao_kpi,
        "confinamento": confinamento_kpi,
        "total_por_tipo": total_por_tipo, "total_ativo": total_ativo,
        "alertas_despesas": alertas_despesas_out, "financeiro_rebanho": financeiro_rebanho,
        "previsao": {"prontos": prontos_prev, "no_prazo_90d": no_prazo_prev},
    }


@router.get("/qtd-pasto")
def qtd_pasto():
    animais = supabase.table("animais").select("pasto_atual,tipo").ilike("status", "ATIVO").not_.is_("pasto_atual", "null").execute().data
    resultado: dict = {}
    for a in animais:
        pasto = a.get("pasto_atual")
        tipo = a.get("tipo")
        if pasto and tipo:
            resultado.setdefault(pasto, {t: 0 for t in _TIPOS})
            if tipo in resultado[pasto]:
                resultado[pasto][tipo] += 1
    return resultado


@router.get("/ganho-peso")
def ganho_peso(ano: int = Query(...)):
    rows = supabase.table("pesagens").select("data,ganho_kg").like("data", f"{ano}-%").execute().data
    resultado = {str(m): 0.0 for m in range(1, 13)}
    for r in rows:
        try:
            mes = int((r.get("data") or "")[:7].split("-")[1])
            resultado[str(mes)] = round(resultado[str(mes)] + (r.get("ganho_kg") or 0), 2)
        except Exception:
            pass
    return resultado


@router.get("/financeiro")
def financeiro(ano: int = Query(...)):
    compras_rows = supabase.table("compras").select("data,valor_total").like("data", f"{ano}-%").execute().data
    vendas_rows = supabase.table("vendas").select("data,valor_total").like("data", f"{ano}-%").execute().data
    compras = {str(m): 0.0 for m in range(1, 13)}
    for r in compras_rows:
        try:
            mes = int((r.get("data") or "")[:7].split("-")[1])
            compras[str(mes)] = round(compras[str(mes)] + (r.get("valor_total") or 0), 2)
        except Exception:
            pass
    vendas = {str(m): 0.0 for m in range(1, 13)}
    for r in vendas_rows:
        try:
            mes = int((r.get("data") or "")[:7].split("-")[1])
            vendas[str(mes)] = round(vendas[str(mes)] + (r.get("valor_total") or 0), 2)
        except Exception:
            pass
    return {"compras": compras, "vendas": vendas}


@router.get("/despesas")
def despesas_relatorio(ano: int = Query(...), status: Optional[str] = Query(None)):
    q = supabase.table("despesas").select("vencimento,tipo,valor").like("vencimento", f"{ano}-%")
    if status:
        q = q.ilike("status", status)
    registros = q.execute().data
    mensal = {str(m): 0.0 for m in range(1, 13)}
    por_tipo: dict = {}
    for d in registros:
        try:
            mes = int((d.get("vencimento") or "")[:7].split("-")[1])
            mensal[str(mes)] = round(mensal[str(mes)] + (d.get("valor") or 0), 2)
        except Exception:
            pass
        cat = d.get("tipo")
        if cat:
            por_tipo[cat] = round(por_tipo.get(cat, 0) + (d.get("valor") or 0), 2)
    return {"mensal": mensal, "por_tipo": por_tipo}


@router.get("/previsao-saida")
def previsao_saida(
    peso_alvo: float = Query(...),
    dias_gmd: int = Query(90),
    status: str = Query("ATIVO"),
    tipo: Optional[str] = Query(None),
    pasto: Optional[str] = Query(None),
    lote: Optional[str] = Query(None),
    preco_arroba: Optional[float] = Query(None),
):
    q = supabase.table("animais").select("*").ilike("status", status)
    if tipo:
        q = q.ilike("tipo", tipo)
    if pasto:
        q = q.ilike("pasto_atual", pasto)
    animais = q.execute().data
    resultado = [_previsao_animal(a, peso_alvo, dias_gmd, preco_arroba, None) for a in animais]
    resultado.sort(key=lambda r: r["data_prevista"] if r["data_prevista"] else "9999-99-99")
    prontos = sum(1 for r in resultado if r["situacao"] == "PRONTO")
    no_prazo = sum(1 for r in resultado if r["situacao"] == "NO_PRAZO")
    medio_prazo = sum(1 for r in resultado if r["situacao"] == "MEDIO_PRAZO")
    longo_prazo = sum(1 for r in resultado if r["situacao"] == "LONGO_PRAZO")
    sem_dados = sum(1 for r in resultado if r["situacao"] in ("SEM_DADOS", "GMD_INVALIDO"))
    gmds_validos = [r["gmd_real"] for r in resultado if r["gmd_real"]]
    gmd_medio = round(sum(gmds_validos) / len(gmds_validos), 3) if gmds_validos else None
    receita_total = sum(r["receita_estimada"] or 0 for r in resultado)
    lucro_total = sum(r["lucro_estimado"] or 0 for r in resultado if r["lucro_estimado"] is not None)
    return {
        "resumo": {
            "total_animais": len(resultado), "prontos": prontos, "no_prazo_90d": no_prazo,
            "medio_prazo": medio_prazo, "longo_prazo": longo_prazo, "sem_dados": sem_dados,
            "gmd_medio_rebanho": gmd_medio,
            "receita_total_estimada": round(receita_total, 2) if preco_arroba else None,
            "lucro_total_estimado": round(lucro_total, 2) if preco_arroba else None,
        },
        "animais": resultado,
    }


@router.get("/mortes")
def mortes(ano: int = Query(...)):
    rows = supabase.table("animais").select("data_morte").ilike("status", "MORTO").like("data_morte", f"{ano}-%").execute().data
    resultado = {str(m): 0 for m in range(1, 13)}
    for r in rows:
        try:
            mes = int((r.get("data_morte") or "")[:7].split("-")[1])
            resultado[str(mes)] += 1
        except Exception:
            pass
    return resultado
