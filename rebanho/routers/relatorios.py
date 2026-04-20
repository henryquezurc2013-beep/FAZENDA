from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Animal, Compra, Config, Despesa, Lote, LoteAnimal, Pesagem, Venda, Chuva, LotePasto, Piquete, LancamentoRacao, EstoqueSuplemento, Suplemento, PlanoNutricional

router = APIRouter()

_TIPOS = ["VACA", "TOURO", "BOI", "GARROTE", "NOVILHA", "BEZERRO", "BEZERRA"]


@router.get("/kpis")
def kpis(db: Session = Depends(get_db)):
    hoje = date.today()
    hoje_iso = hoje.isoformat()
    hoje_str = hoje.strftime("%Y-%m")

    # ── Rebanho ──────────────────────────────────────────────────────────
    contagens = (
        db.query(Animal.tipo, func.count(Animal.id))
        .filter(Animal.status.ilike("ATIVO"))
        .group_by(Animal.tipo)
        .all()
    )
    total_por_tipo = {t: 0 for t in _TIPOS}
    for tipo, qtd in contagens:
        if tipo in total_por_tipo:
            total_por_tipo[tipo] = qtd
    total_ativo = sum(total_por_tipo.values())

    rebanho = {"total_ativo": total_ativo, "total_por_tipo": total_por_tipo}

    # ── Financeiro ───────────────────────────────────────────────────────
    ativos_com_compra = db.query(Animal).filter(
        Animal.status.ilike("ATIVO"), Animal.valor_compra > 0
    ).all()
    valor_total = sum(a.valor_compra or 0 for a in ativos_com_compra)
    custos_kg  = [a.custo_kg    for a in ativos_com_compra if a.custo_kg]
    custos_arr = [a.custo_arroba for a in ativos_com_compra if a.custo_arroba]
    mais_caro  = max(ativos_com_compra, key=lambda a: a.valor_compra or 0) if ativos_com_compra else None
    financeiro_rebanho = {
        "valor_total_compras_animais": round(valor_total, 2),
        "custo_medio_kg":     round(sum(custos_kg)/len(custos_kg), 2)   if custos_kg  else None,
        "custo_medio_arroba": round(sum(custos_arr)/len(custos_arr), 2) if custos_arr else None,
        "animal_mais_caro": {
            "brinco": mais_caro.brinco, "nome": mais_caro.nome,
            "valor_compra": mais_caro.valor_compra
        } if mais_caro else None,
    }

    # ── Config ───────────────────────────────────────────────────────────
    cfg_rows = db.query(Config).all()
    cfg = {r.chave: r.valor for r in cfg_rows}
    peso_alvo_padrao  = float(cfg.get("peso_alvo_padrao",  "480"))
    preco_arr_padrao  = float(cfg.get("preco_arroba_padrao", "0") or "0")

    # ── Previsão de saída ────────────────────────────────────────────────
    animais_ativos = db.query(Animal).filter(Animal.status.ilike("ATIVO")).all()
    prev_results = [_previsao_animal(a, peso_alvo_padrao, 90,
                                     preco_arr_padrao if preco_arr_padrao else None, db)
                    for a in animais_ativos]

    prontos_prev = sum(1 for r in prev_results if r["situacao"] == "PRONTO")
    no_prazo_prev = sum(1 for r in prev_results if r["situacao"] == "NO_PRAZO")
    medio_prazo_prev = sum(1 for r in prev_results if r["situacao"] == "MEDIO_PRAZO")
    longo_prazo_prev = sum(1 for r in prev_results if r["situacao"] == "LONGO_PRAZO")
    sem_dados_prev = sum(1 for r in prev_results if r["situacao"] in ("SEM_DADOS", "GMD_INVALIDO"))

    animais_proximos = sorted(
        [r for r in prev_results if r["data_prevista"]],
        key=lambda r: r["data_prevista"]
    )[:5]

    previsao_saida = {
        "peso_alvo": peso_alvo_padrao,
        "prontos": prontos_prev,
        "no_prazo_90d": no_prazo_prev,
        "medio_prazo": medio_prazo_prev,
        "longo_prazo": longo_prazo_prev,
        "sem_dados": sem_dados_prev,
        "animais_proximos": [
            {
                "brinco": r["brinco"], "nome": r["nome"], "tipo": r["tipo"],
                "peso_atual": r["peso_atual"], "peso_alvo": r["peso_alvo"],
                "dias_restantes": r["dias_restantes"], "situacao": r["situacao"],
                "semaforo": r["semaforo"], "data_prevista": r["data_prevista"],
                "gmd_real": r["gmd_real"],
            }
            for r in animais_proximos
        ],
    }

    # ── Pastagem ─────────────────────────────────────────────────────────
    chuvas = db.query(Chuva).all()
    chuva_mes = round(sum(c.mm_chuva for c in chuvas if c.data and c.data[:7] == hoje_str), 1)

    from routers.pastagem import semaforo_piquete as _semaforo
    piquetes = db.query(Piquete).all()
    sem_counts = {s: 0 for s in ("VERDE", "AMARELO", "VERMELHO", "SAIR_AGORA", "OCUPADO", "SEM_DADOS")}
    piquetes_lista = []
    for pq in piquetes:
        s_info = _semaforo(pq.id, db)
        s = s_info["semaforo"]
        sem_counts[s] = sem_counts.get(s, 0) + 1
        piquetes_lista.append({"id": pq.id, "nome": pq.nome, "semaforo": s,
                                "area_ha": pq.area_ha, "status": pq.status})

    pastagem_kpi = {
        "verde": sem_counts["VERDE"],
        "amarelo": sem_counts["AMARELO"],
        "vermelho": sem_counts["VERMELHO"],
        "sair_agora": sem_counts["SAIR_AGORA"],
        "ocupado": sem_counts["OCUPADO"],
        "sem_dados": sem_counts["SEM_DADOS"],
        "alerta_seca": chuva_mes < 50,
        "chuva_mes_mm": chuva_mes,
        "piquetes": piquetes_lista,
    }

    # ── Lotes ────────────────────────────────────────────────────────────
    lotes_ativos = db.query(Lote).filter(Lote.status.ilike("ATIVO")).all()
    lotes_lista = []
    for lt in lotes_ativos:
        qtd = db.query(LoteAnimal).filter(
            LoteAnimal.lote_id == lt.id, LoteAnimal.status.ilike("ATIVO")
        ).count()
        lotes_lista.append({
            "id": lt.id, "nome": lt.nome, "categoria": lt.categoria,
            "qtd_animais": qtd, "ua_total": lt.ua_total, "ua_ha": lt.ua_ha,
            "classificacao": lt.classificacao,
        })
    lotes_kpi = {"total_ativos": len(lotes_ativos), "lista": lotes_lista}

    # ── Alertas automáticos ──────────────────────────────────────────────
    alertas_geradas = []

    # Despesas vencidas PENDENTE
    despesas_venc = (
        db.query(Despesa)
        .filter(Despesa.status.ilike("PENDENTE"), Despesa.vencimento < hoje_iso)
        .order_by(Despesa.vencimento)
        .all()
    )
    for d in despesas_venc:
        alertas_geradas.append({
            "nivel": "CRITICO", "icone": "🔴",
            "msg": f"Despesa vencida: {d.tipo} — {d.descricao} ({d.vencimento})",
            "valor": d.valor,
        })

    # Despesas vencendo em 7 dias
    limite_7d = (hoje + timedelta(days=7)).isoformat()
    despesas_prox = (
        db.query(Despesa)
        .filter(
            Despesa.status.ilike("PENDENTE"),
            Despesa.vencimento >= hoje_iso,
            Despesa.vencimento <= limite_7d,
        )
        .all()
    )
    for d in despesas_prox:
        alertas_geradas.append({
            "nivel": "ATENCAO", "icone": "🟡",
            "msg": f"Vence em 7 dias: {d.tipo} — {d.descricao} ({d.vencimento})",
            "valor": d.valor,
        })

    # Piquetes SAIR_AGORA
    if sem_counts["SAIR_AGORA"] > 0:
        alertas_geradas.append({
            "nivel": "CRITICO", "icone": "🔴",
            "msg": f"{sem_counts['SAIR_AGORA']} piquete(s) precisam ser esvaziados agora",
            "valor": None,
        })

    # Alerta seca
    if chuva_mes < 30:
        alertas_geradas.append({
            "nivel": "CRITICO", "icone": "🔴",
            "msg": f"Seca crítica: apenas {chuva_mes} mm de chuva no mês",
            "valor": None,
        })
    elif chuva_mes < 50:
        alertas_geradas.append({
            "nivel": "ATENCAO", "icone": "🟡",
            "msg": f"Chuva abaixo do ideal: {chuva_mes} mm no mês",
            "valor": None,
        })

    # Animais prontos para saída
    if prontos_prev > 0:
        alertas_geradas.append({
            "nivel": "INFO", "icone": "🟢",
            "msg": f"{prontos_prev} animal(is) atingiu o peso alvo de {peso_alvo_padrao:.0f} kg",
            "valor": None,
        })

    # ── Últimas pesagens ─────────────────────────────────────────────────
    ultimas = (
        db.query(Pesagem)
        .order_by(Pesagem.data_pesagem.desc())
        .limit(5)
        .all()
    )
    pesagens_out = [
        {"brinco": p.brinco, "data": p.data_pesagem, "peso": p.peso, "ganho_kg": p.ganho_kg}
        for p in ultimas
    ]

    # Legacy alertas_despesas for compat
    alertas_despesas_out = [
        {"id": d.id, "tipo": d.tipo, "descricao": d.descricao,
         "valor": d.valor, "vencimento": d.vencimento}
        for d in despesas_venc
    ]

    # ── Nutrição ─────────────────────────────────────────────────────────
    planos_ativos = db.query(PlanoNutricional).filter(
        PlanoNutricional.status == "ATIVO"
    ).count()
    mes_ini = hoje_str + "-01"
    custo_nut_mes = db.query(func.sum(LancamentoRacao.custo_real)).filter(
        LancamentoRacao.data >= mes_ini
    ).scalar() or 0
    sups_ativos = db.query(Suplemento).filter(Suplemento.ativo == True).all()
    estoque_critico = 0
    for s in sups_ativos:
        from routers.nutricao import _saldo_estoque, _consumo_medio_diario
        saldo = _saldo_estoque(db, s.id)
        cmd = _consumo_medio_diario(db, s.id)
        if cmd and cmd > 0 and (saldo / cmd) < 7:
            estoque_critico += 1
    nutricao_kpi = {
        "planos_ativos": planos_ativos,
        "custo_mes": round(float(custo_nut_mes), 2),
        "estoque_critico": estoque_critico,
        "total_suplementos": len(sups_ativos),
    }

    return {
        # New structured keys
        "rebanho": rebanho,
        "financeiro": financeiro_rebanho,
        "previsao_saida": previsao_saida,
        "pastagem": pastagem_kpi,
        "lotes": lotes_kpi,
        "alertas": alertas_geradas,
        "ultimas_pesagens": pesagens_out,
        "config": cfg,
        "nutricao": nutricao_kpi,
        # Legacy keys (kept for animais.html compat)
        "total_por_tipo": total_por_tipo,
        "total_ativo": total_ativo,
        "alertas_despesas": alertas_despesas_out,
        "financeiro_rebanho": financeiro_rebanho,
        "previsao": {"prontos": prontos_prev, "no_prazo_90d": no_prazo_prev},
    }


@router.get("/qtd-pasto")
def qtd_pasto(db: Session = Depends(get_db)):
    rows = (
        db.query(Animal.pasto, Animal.tipo, func.count(Animal.id))
        .filter(Animal.status.ilike("ATIVO"), Animal.pasto.isnot(None))
        .group_by(Animal.pasto, Animal.tipo)
        .all()
    )
    resultado: dict = {}
    for pasto, tipo, qtd in rows:
        resultado.setdefault(pasto, {t: 0 for t in _TIPOS})
        if tipo in resultado[pasto]:
            resultado[pasto][tipo] = qtd
    return resultado


@router.get("/ganho-peso")
def ganho_peso(ano: int = Query(...), db: Session = Depends(get_db)):
    rows = (
        db.query(Pesagem.mes, func.sum(Pesagem.ganho_kg))
        .filter(Pesagem.ano == ano)
        .group_by(Pesagem.mes)
        .all()
    )
    resultado = {str(m): 0.0 for m in range(1, 13)}
    for mes, total in rows:
        if mes:
            resultado[str(mes)] = round(total or 0, 2)
    return resultado


@router.get("/financeiro")
def financeiro(ano: int = Query(...), db: Session = Depends(get_db)):
    compras_rows = (
        db.query(Compra.mes, func.sum(Compra.valor_total))
        .filter(Compra.ano == ano)
        .group_by(Compra.mes)
        .all()
    )
    vendas_rows = (
        db.query(Venda.mes, func.sum(Venda.valor_total))
        .filter(Venda.ano == ano)
        .group_by(Venda.mes)
        .all()
    )

    compras = {str(m): 0.0 for m in range(1, 13)}
    for mes, total in compras_rows:
        if mes:
            compras[str(mes)] = round(total or 0, 2)

    vendas = {str(m): 0.0 for m in range(1, 13)}
    for mes, total in vendas_rows:
        if mes:
            vendas[str(mes)] = round(total or 0, 2)

    return {"compras": compras, "vendas": vendas}


@router.get("/despesas")
def despesas_relatorio(
    ano: int = Query(...),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Despesa).filter(Despesa.ano == ano)
    if status:
        q = q.filter(Despesa.status.ilike(status))
    registros = q.all()

    mensal = {str(m): 0.0 for m in range(1, 13)}
    por_tipo: dict = {}
    for d in registros:
        if d.mes:
            mensal[str(d.mes)] = round(mensal[str(d.mes)] + (d.valor or 0), 2)
        if d.tipo:
            por_tipo[d.tipo] = round(por_tipo.get(d.tipo, 0) + (d.valor or 0), 2)

    return {"mensal": mensal, "por_tipo": por_tipo}


def _calcular_gmd(brinco: str, dias_janela: int, db: Session):
    hoje = date.today()
    cutoff = (hoje - timedelta(days=dias_janela)).isoformat() if dias_janela > 0 else None

    q = db.query(Pesagem).filter(Pesagem.brinco == brinco).order_by(Pesagem.data_pesagem.asc())
    if cutoff:
        q_janela = q.filter(Pesagem.data_pesagem >= cutoff).all()
    else:
        q_janela = []

    pesagens = q_janela if len(q_janela) >= 2 else q.all()

    if len(pesagens) < 2:
        return None, len(pesagens)

    total_ganho = sum(p.ganho_kg or 0 for p in pesagens)
    try:
        d_ini = date.fromisoformat(pesagens[0].data_pesagem)
        d_fim = date.fromisoformat(pesagens[-1].data_pesagem)
        dias = (d_fim - d_ini).days
    except Exception:
        dias = 0

    if dias <= 0:
        return None, len(pesagens)

    return round(total_ganho / dias, 4), len(pesagens)


def _previsao_animal(animal: Animal, peso_alvo: float, dias_gmd: int, preco_arroba: float | None, db: Session) -> dict:
    hoje = date.today()
    peso_atual = animal.peso_atual or 0
    gmd, qtd_pes = _calcular_gmd(animal.brinco, dias_gmd, db)

    arrobas = round(peso_alvo / 15, 2)

    if peso_atual >= peso_alvo:
        situacao = "PRONTO"
        semaforo = "VERDE"
        dias_rest = 0
        data_prev = hoje.isoformat()
        data_otim = hoje.isoformat()
        data_pess = hoje.isoformat()
    elif gmd is None:
        situacao = "SEM_DADOS"
        semaforo = "CINZA"
        dias_rest = None
        data_prev = data_otim = data_pess = None
    elif gmd <= 0:
        situacao = "GMD_INVALIDO"
        semaforo = "CINZA"
        dias_rest = None
        data_prev = data_otim = data_pess = None
    else:
        diferenca = peso_alvo - peso_atual
        dias_rest = round(diferenca / gmd)
        if dias_rest > 730:
            situacao = "LONGO_PRAZO"
            semaforo = "CINZA"
        elif dias_rest > 180:
            situacao = "LONGO_PRAZO"
            semaforo = "CINZA"
        elif dias_rest > 90:
            situacao = "MEDIO_PRAZO"
            semaforo = "AMARELO"
        else:
            situacao = "NO_PRAZO"
            semaforo = "VERDE"
        data_prev = (hoje + timedelta(days=dias_rest)).isoformat()
        dias_otim = round(diferenca / (gmd * 1.15))
        dias_pess = round(diferenca / (gmd * 0.85))
        data_otim = (hoje + timedelta(days=dias_otim)).isoformat()
        data_pess = (hoje + timedelta(days=dias_pess)).isoformat()

    receita = lucro = None
    if preco_arroba and situacao not in ("SEM_DADOS", "GMD_INVALIDO"):
        receita = round(arrobas * preco_arroba, 2)
        if animal.valor_compra:
            lucro = round(receita - animal.valor_compra, 2)

    return {
        "brinco": animal.brinco,
        "nome": animal.nome,
        "tipo": animal.tipo,
        "raca": animal.raca,
        "pasto": animal.pasto,
        "lote": animal.lote,
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
        "valor_compra": getattr(animal, "valor_compra", None),
        "situacao": situacao,
        "semaforo": semaforo,
    }


@router.get("/previsao-saida")
def previsao_saida(
    peso_alvo: float = Query(...),
    dias_gmd: int = Query(90),
    status: str = Query("ATIVO"),
    tipo: Optional[str] = Query(None),
    pasto: Optional[str] = Query(None),
    lote: Optional[str] = Query(None),
    preco_arroba: Optional[float] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Animal).filter(Animal.status.ilike(status))
    if tipo:
        q = q.filter(Animal.tipo.ilike(tipo))
    if pasto:
        q = q.filter(Animal.pasto.ilike(pasto))
    if lote:
        q = q.filter(Animal.lote.ilike(f"%{lote}%"))

    animais = q.all()
    resultado = [_previsao_animal(a, peso_alvo, dias_gmd, preco_arroba, db) for a in animais]

    def sort_key(r):
        if r["data_prevista"]:
            return r["data_prevista"]
        return "9999-99-99"

    resultado.sort(key=sort_key)

    prontos     = sum(1 for r in resultado if r["situacao"] == "PRONTO")
    no_prazo    = sum(1 for r in resultado if r["situacao"] == "NO_PRAZO")
    medio_prazo = sum(1 for r in resultado if r["situacao"] == "MEDIO_PRAZO")
    longo_prazo = sum(1 for r in resultado if r["situacao"] == "LONGO_PRAZO")
    sem_dados   = sum(1 for r in resultado if r["situacao"] in ("SEM_DADOS", "GMD_INVALIDO"))

    gmds_validos = [r["gmd_real"] for r in resultado if r["gmd_real"]]
    gmd_medio = round(sum(gmds_validos) / len(gmds_validos), 3) if gmds_validos else None

    receita_total = sum(r["receita_estimada"] or 0 for r in resultado)
    lucro_total   = sum(r["lucro_estimado"] or 0 for r in resultado if r["lucro_estimado"] is not None)

    return {
        "resumo": {
            "total_animais": len(resultado),
            "prontos": prontos,
            "no_prazo_90d": no_prazo,
            "medio_prazo": medio_prazo,
            "longo_prazo": longo_prazo,
            "sem_dados": sem_dados,
            "gmd_medio_rebanho": gmd_medio,
            "receita_total_estimada": round(receita_total, 2) if preco_arroba else None,
            "lucro_total_estimado": round(lucro_total, 2) if preco_arroba else None,
        },
        "animais": resultado,
    }


@router.get("/mortes")
def mortes(ano: int = Query(...), db: Session = Depends(get_db)):
    rows = (
        db.query(Animal.mes_morte, func.count(Animal.id))
        .filter(Animal.ano_morte == ano, Animal.status.ilike("MORTO"))
        .group_by(Animal.mes_morte)
        .all()
    )
    resultado = {str(m): 0 for m in range(1, 13)}
    for mes, qtd in rows:
        if mes:
            resultado[str(mes)] = qtd
    return resultado
