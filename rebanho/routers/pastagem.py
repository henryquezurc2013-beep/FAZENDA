import json as _json
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AdubacaoPastagem, Animal, Chuva, Lote, LoteAnimal, LotePasto,
    ManejoPastagem, MedicaoPasto, Pesagem, Pasto, Piquete,
)

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


def semaforo_piquete(piquete_id: int, db: Session) -> dict:
    piquete = db.query(Piquete).filter(Piquete.id == piquete_id).first()
    if not piquete:
        return {"semaforo": "SEM_DADOS", "altura_atual": None,
                "dias_descanso": 0, "dias_ocupacao": 0, "mensagem": "Piquete não encontrado"}

    hoje = date.today()

    # Medição mais recente
    medicao = (
        db.query(MedicaoPasto)
        .filter(MedicaoPasto.piquete_id == piquete_id)
        .order_by(MedicaoPasto.data.desc(), MedicaoPasto.id.desc())
        .first()
    )

    altura_atual = None
    dias_sem_medicao = 999
    if medicao:
        try:
            d_med = date.fromisoformat(medicao.data)
            dias_sem_medicao = (hoje - d_med).days
            altura_atual = medicao.altura_cm
        except Exception:
            pass

    # Lote ativo
    lote_ativo = (
        db.query(LotePasto)
        .filter(LotePasto.piquete_id == piquete_id, LotePasto.status == "ATIVO")
        .order_by(LotePasto.data_entrada.desc())
        .first()
    )

    # Último manejo para calcular dias de descanso
    ultimo_manejo = (
        db.query(ManejoPastagem)
        .filter(ManejoPastagem.piquete_id == piquete_id,
                ManejoPastagem.data_saida.isnot(None))
        .order_by(ManejoPastagem.data_saida.desc())
        .first()
    )

    dias_descanso = 0
    if ultimo_manejo and ultimo_manejo.data_saida:
        try:
            d_saida = date.fromisoformat(ultimo_manejo.data_saida)
            dias_descanso = (hoje - d_saida).days
        except Exception:
            pass

    dias_ocupacao = 0
    if lote_ativo and lote_ativo.data_entrada:
        try:
            d_ent = date.fromisoformat(lote_ativo.data_entrada)
            dias_ocupacao = (hoje - d_ent).days
        except Exception:
            pass

    alt_entrada = piquete.altura_entrada_cm or 35
    alt_saida   = piquete.altura_saida_cm or 15
    desc_alvo   = piquete.dias_descanso_alvo or 28

    # Sem medição recente
    if dias_sem_medicao > 14:
        return {
            "semaforo": "SEM_DADOS",
            "altura_atual": altura_atual,
            "dias_descanso": dias_descanso,
            "dias_ocupacao": dias_ocupacao,
            "lote": lote_ativo.lote if lote_ativo else None,
            "mensagem": f"Sem medição há {dias_sem_medicao} dias. Medir o capim.",
        }

    # Com lote (OCUPADO)
    if lote_ativo:
        if (altura_atual is not None and altura_atual <= alt_saida) or dias_ocupacao >= desc_alvo:
            motivo = (f"Altura: {altura_atual} cm (mínimo {alt_saida} cm)"
                      if altura_atual and altura_atual <= alt_saida
                      else f"Ocupação: {dias_ocupacao} dias (alvo {desc_alvo} dias)")
            return {
                "semaforo": "SAIR_AGORA",
                "altura_atual": altura_atual,
                "dias_descanso": dias_descanso,
                "dias_ocupacao": dias_ocupacao,
                "lote": lote_ativo.lote,
                "mensagem": f"Retirar o lote agora! {motivo}.",
            }
        return {
            "semaforo": "OCUPADO",
            "altura_atual": altura_atual,
            "dias_descanso": dias_descanso,
            "dias_ocupacao": dias_ocupacao,
            "lote": lote_ativo.lote,
            "mensagem": f"Ocupado por {lote_ativo.lote}. {dias_ocupacao} dias de ocupação.",
        }

    # Sem lote (em descanso)
    pasto_pronto   = altura_atual is not None and altura_atual >= alt_entrada
    descanso_ok    = dias_descanso >= desc_alvo

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


def _pasto_dict(p: Pasto, db: Session) -> dict:
    qtd = db.query(func.count(Piquete.id)).filter(Piquete.pasto_id == p.id).scalar() or 0
    return {
        "id": p.id, "nome": p.nome, "area_ha": p.area_ha,
        "tipo_capim": p.tipo_capim, "sistema": p.sistema,
        "status": p.status, "obs": p.obs, "qtd_piquetes": qtd,
    }


def _pq_coords(pq: Piquete):
    if not pq.coordenadas:
        return None
    try:
        return _json.loads(pq.coordenadas)
    except Exception:
        return None


def _piquete_dict(pq: Piquete, db: Session, incluir_semaforo: bool = True) -> dict:
    d = {
        "id": pq.id, "pasto_id": pq.pasto_id, "nome": pq.nome,
        "area_ha": pq.area_ha, "tipo_capim": pq.tipo_capim,
        "altura_entrada_cm": pq.altura_entrada_cm,
        "altura_saida_cm": pq.altura_saida_cm,
        "dias_descanso_alvo": pq.dias_descanso_alvo,
        "tem_bebedouro": pq.tem_bebedouro, "tem_cocho": pq.tem_cocho,
        "tem_sombra": pq.tem_sombra, "status": pq.status, "obs": pq.obs,
        "coordenadas": _pq_coords(pq),
        "cor_mapa": pq.cor_mapa or '#2E7D32',
        "icone_mapa": pq.icone_mapa or '🌿',
    }
    pasto = db.query(Pasto).filter(Pasto.id == pq.pasto_id).first()
    d["pasto_nome"] = pasto.nome if pasto else ""
    if incluir_semaforo:
        d["semaforo"] = semaforo_piquete(pq.id, db)
    return d


_COR_SEM = {
    "VERDE":     "#2E7D32",
    "AMARELO":   "#F9A825",
    "VERMELHO":  "#C62828",
    "SAIR_AGORA":"#B71C1C",
    "OCUPADO":   "#1565C0",
    "SEM_DADOS": "#757575",
}


def _piquete_mapa_dict(pq: Piquete, db: Session) -> dict:
    sem    = semaforo_piquete(pq.id, db)
    pasto  = db.query(Pasto).filter(Pasto.id == pq.pasto_id).first()
    lote_a = (
        db.query(LotePasto)
        .filter(LotePasto.piquete_id == pq.id, LotePasto.status == "ATIVO")
        .order_by(LotePasto.data_entrada.desc())
        .first()
    )
    med = (
        db.query(MedicaoPasto)
        .filter(MedicaoPasto.piquete_id == pq.id)
        .order_by(MedicaoPasto.data.desc())
        .first()
    )
    ua_ha = None
    classificacao_ua = None
    if lote_a and pq.area_ha:
        ua = (lote_a.qtd_cabecas or 0) * (lote_a.peso_medio_kg or 380) / 450
        ua_ha = round(ua / pq.area_ha, 2)
        if   ua_ha < 1.0: classificacao_ua = "LEVE"
        elif ua_ha < 2.5: classificacao_ua = "IDEAL"
        elif ua_ha < 4.0: classificacao_ua = "ALTA"
        else:             classificacao_ua = "CRITICA"

    sem_str = sem.get("semaforo", "SEM_DADOS")
    return {
        "id": pq.id,
        "nome": pq.nome,
        "pasto": pasto.nome if pasto else "",
        "coordenadas": _pq_coords(pq),
        "area_ha": pq.area_ha,
        "tipo_capim": pq.tipo_capim,
        "cor_mapa": pq.cor_mapa or '#2E7D32',
        "semaforo": sem_str,
        "cor_semaforo": _COR_SEM.get(sem_str, "#757575"),
        "altura_atual": sem.get("altura_atual"),
        "dias_descanso": sem.get("dias_descanso", 0),
        "dias_ocupacao": sem.get("dias_ocupacao", 0),
        "lote_atual": lote_a.lote if lote_a else None,
        "qtd_animais": lote_a.qtd_cabecas if lote_a else None,
        "ua_ha": ua_ha,
        "classificacao_ua": classificacao_ua,
        "ultima_medicao": med.data if med else None,
        "mensagem": sem.get("mensagem", ""),
    }


# ── PASTOS ───────────────────────────────────────────────────────────

@router.get("/pastos")
def listar_pastos(db: Session = Depends(get_db)):
    pastos = db.query(Pasto).order_by(Pasto.nome).all()
    return [_pasto_dict(p, db) for p in pastos]


@router.post("/pastos")
def criar_pasto(body: dict, db: Session = Depends(get_db)):
    if not body.get("nome"):
        raise HTTPException(status_code=400, detail="Nome é obrigatório.")
    existente = db.query(Pasto).filter(Pasto.nome.ilike(body["nome"])).first()
    if existente:
        raise HTTPException(status_code=400, detail="Já existe um pasto com este nome.")
    p = Pasto(
        nome=body["nome"], area_ha=body.get("area_ha"),
        tipo_capim=body.get("tipo_capim"), sistema=body.get("sistema"),
        status=body.get("status", "ATIVO"), obs=body.get("obs"),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _pasto_dict(p, db)


@router.put("/pastos/{id}")
def editar_pasto(id: int, body: dict, db: Session = Depends(get_db)):
    p = db.query(Pasto).filter(Pasto.id == id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Pasto não encontrado.")
    for campo in ["nome", "area_ha", "tipo_capim", "sistema", "status", "obs"]:
        if campo in body:
            setattr(p, campo, body[campo])
    db.commit()
    return _pasto_dict(p, db)


@router.delete("/pastos/{id}")
def excluir_pasto(id: int, db: Session = Depends(get_db)):
    p = db.query(Pasto).filter(Pasto.id == id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Pasto não encontrado.")
    qtd = db.query(func.count(Piquete.id)).filter(Piquete.pasto_id == id).scalar() or 0
    if qtd > 0:
        raise HTTPException(status_code=400, detail="Não é possível excluir pasto com piquetes cadastrados.")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ── PIQUETES ─────────────────────────────────────────────────────────

@router.get("/piquetes")
def listar_piquetes(
    pasto_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Piquete)
    if pasto_id:
        q = q.filter(Piquete.pasto_id == pasto_id)
    if status:
        q = q.filter(Piquete.status.ilike(status))
    return [_piquete_dict(pq, db) for pq in q.order_by(Piquete.nome).all()]


@router.post("/piquetes")
def criar_piquete(body: dict, db: Session = Depends(get_db)):
    if not body.get("nome"):
        raise HTTPException(status_code=400, detail="Nome é obrigatório.")
    pq = Piquete(
        pasto_id=body.get("pasto_id"), nome=body["nome"],
        area_ha=body.get("area_ha"), tipo_capim=body.get("tipo_capim"),
        altura_entrada_cm=body.get("altura_entrada_cm"),
        altura_saida_cm=body.get("altura_saida_cm"),
        dias_descanso_alvo=body.get("dias_descanso_alvo"),
        tem_bebedouro=body.get("tem_bebedouro", False),
        tem_cocho=body.get("tem_cocho", False),
        tem_sombra=body.get("tem_sombra", False),
        status=body.get("status", "DISPONIVEL"), obs=body.get("obs"),
    )
    db.add(pq)
    db.commit()
    db.refresh(pq)
    return _piquete_dict(pq, db)


@router.put("/piquetes/{id}")
def editar_piquete(id: int, body: dict, db: Session = Depends(get_db)):
    pq = db.query(Piquete).filter(Piquete.id == id).first()
    if not pq:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")
    for campo in ["pasto_id", "nome", "area_ha", "tipo_capim", "altura_entrada_cm",
                  "altura_saida_cm", "dias_descanso_alvo", "tem_bebedouro",
                  "tem_cocho", "tem_sombra", "status", "obs"]:
        if campo in body:
            setattr(pq, campo, body[campo])
    db.commit()
    return _piquete_dict(pq, db)


@router.delete("/piquetes/{id}")
def excluir_piquete(id: int, db: Session = Depends(get_db)):
    pq = db.query(Piquete).filter(Piquete.id == id).first()
    if not pq:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")
    hist = db.query(func.count(ManejoPastagem.id)).filter(ManejoPastagem.piquete_id == id).scalar() or 0
    if hist > 0:
        raise HTTPException(status_code=400, detail="Piquete tem histórico de manejo e não pode ser excluído.")
    db.delete(pq)
    db.commit()
    return {"ok": True}


@router.get("/piquetes/{id}/semaforo")
def semaforo_endpoint(id: int, db: Session = Depends(get_db)):
    pq = db.query(Piquete).filter(Piquete.id == id).first()
    if not pq:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")
    return semaforo_piquete(id, db)


@router.put("/piquetes/{id}/coordenadas")
def salvar_coordenadas(id: int, body: dict, db: Session = Depends(get_db)):
    pq = db.query(Piquete).filter(Piquete.id == id).first()
    if not pq:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")
    coords = body.get("coordenadas")
    pq.coordenadas = _json.dumps(coords) if coords else None
    db.commit()
    return {"ok": True, "id": id}


# ── MAPA ─────────────────────────────────────────────────────────────

@router.get("/mapa")
def mapa_dados(db: Session = Depends(get_db)):
    piquetes = db.query(Piquete).order_by(Piquete.nome).all()
    piquetes_data = [_piquete_mapa_dict(pq, db) for pq in piquetes]

    # Centro: média dos vértices ou fallback
    todas_coords = [c for pd in piquetes_data if pd["coordenadas"] for c in pd["coordenadas"]]
    if todas_coords:
        lat_c = round(sum(c[0] for c in todas_coords) / len(todas_coords), 6)
        lng_c = round(sum(c[1] for c in todas_coords) / len(todas_coords), 6)
    else:
        lat_c, lng_c = -15.71, -47.92

    # Chuva do mês
    ini_mes = date.today().replace(day=1).isoformat()
    mm_mes  = db.query(func.sum(Chuva.mm_chuva)).filter(Chuva.data >= ini_mes).scalar() or 0

    # Melhor ganho/ha
    melhor = (
        db.query(ManejoPastagem.piquete_id,
                 func.avg(ManejoPastagem.ganho_ha_kg).label("avg_g"))
        .filter(ManejoPastagem.data_saida.isnot(None),
                ManejoPastagem.ganho_ha_kg.isnot(None))
        .group_by(ManejoPastagem.piquete_id)
        .order_by(func.avg(ManejoPastagem.ganho_ha_kg).desc())
        .first()
    )
    melhor_piquete = None
    if melhor:
        pq_m = db.query(Piquete).filter(Piquete.id == melhor.piquete_id).first()
        if pq_m:
            melhor_piquete = {"nome": pq_m.nome, "ganho_ha": round(melhor.avg_g, 1)}

    # UA/ha média geral
    lotes_ativos = db.query(LotePasto).filter(LotePasto.status == "ATIVO").all()
    ua_total = sum((lt.qtd_cabecas or 0) * (lt.peso_medio_kg or 380) / 450 for lt in lotes_ativos)
    area_tot = sum(pq.area_ha or 0 for pq in piquetes)
    ua_ha_media = round(ua_total / area_tot, 2) if area_tot > 0 else None

    # Próximo a ficar pronto (AMARELO com mais dias de descanso)
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
def exportar_geojson(db: Session = Depends(get_db)):
    piquetes = db.query(Piquete).order_by(Piquete.nome).all()
    features = []
    for pq in piquetes:
        coords = _pq_coords(pq)
        if not coords:
            continue
        geo_ring = [[c[1], c[0]] for c in coords]  # GeoJSON: [lng, lat]
        geo_ring.append(geo_ring[0])                # fechar anel
        sem = semaforo_piquete(pq.id, db)
        features.append({
            "type": "Feature",
            "properties": {
                "id": pq.id, "nome": pq.nome,
                "semaforo": sem.get("semaforo", "SEM_DADOS"),
                "area_ha": pq.area_ha, "tipo_capim": pq.tipo_capim,
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
    db: Session = Depends(get_db),
):
    q = db.query(MedicaoPasto)
    if piquete_id:
        q = q.filter(MedicaoPasto.piquete_id == piquete_id)
    if data_ini:
        q = q.filter(MedicaoPasto.data >= data_ini)
    if data_fim:
        q = q.filter(MedicaoPasto.data <= data_fim)
    rows = q.order_by(MedicaoPasto.data.desc()).all()

    result = []
    for m in rows:
        pq = db.query(Piquete).filter(Piquete.id == m.piquete_id).first()
        result.append({
            "id": m.id, "data": m.data, "piquete_id": m.piquete_id,
            "piquete_nome": pq.nome if pq else "",
            "altura_cm": m.altura_cm, "massa_estimada": m.massa_estimada,
            "cobertura_pct": m.cobertura_pct, "falhas_pct": m.falhas_pct,
            "planta_invasora": m.planta_invasora, "condicao": m.condicao,
            "responsavel": m.responsavel, "obs": m.obs,
        })
    return result


@router.post("/medicoes")
def criar_medicao(body: dict, db: Session = Depends(get_db)):
    if not body.get("piquete_id") or body.get("altura_cm") is None:
        raise HTTPException(status_code=400, detail="piquete_id e altura_cm são obrigatórios.")
    m = MedicaoPasto(
        data=body.get("data", date.today().isoformat()),
        piquete_id=body["piquete_id"],
        altura_cm=body["altura_cm"],
        massa_estimada=body.get("massa_estimada"),
        cobertura_pct=body.get("cobertura_pct"),
        falhas_pct=body.get("falhas_pct"),
        planta_invasora=body.get("planta_invasora"),
        condicao=body.get("condicao"),
        responsavel=body.get("responsavel"),
        obs=body.get("obs"),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    pq = db.query(Piquete).filter(Piquete.id == m.piquete_id).first()
    return {"id": m.id, "data": m.data, "piquete_nome": pq.nome if pq else "", **body}


@router.put("/medicoes/{id}")
def editar_medicao(id: int, body: dict, db: Session = Depends(get_db)):
    m = db.query(MedicaoPasto).filter(MedicaoPasto.id == id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Medição não encontrada.")
    for campo in ["data", "piquete_id", "altura_cm", "massa_estimada", "cobertura_pct",
                  "falhas_pct", "planta_invasora", "condicao", "responsavel", "obs"]:
        if campo in body:
            setattr(m, campo, body[campo])
    db.commit()
    return {"id": m.id, "ok": True}


@router.delete("/medicoes/{id}")
def excluir_medicao(id: int, db: Session = Depends(get_db)):
    m = db.query(MedicaoPasto).filter(MedicaoPasto.id == id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Medição não encontrada.")
    db.delete(m)
    db.commit()
    return {"ok": True}


# ── MANEJO (ENTRADAS E SAÍDAS) ───────────────────────────────────────

@router.get("/manejo")
def listar_manejo(
    piquete_id: Optional[int] = Query(None),
    lote: Optional[str] = Query(None),
    data_ini: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ManejoPastagem)
    if piquete_id:
        q = q.filter(ManejoPastagem.piquete_id == piquete_id)
    if lote:
        q = q.filter(ManejoPastagem.lote.ilike(f"%{lote}%"))
    if data_ini:
        q = q.filter(ManejoPastagem.data_entrada >= data_ini)
    if data_fim:
        q = q.filter(ManejoPastagem.data_entrada <= data_fim)
    rows = q.order_by(ManejoPastagem.data_entrada.desc()).all()

    result = []
    for m in rows:
        pq = db.query(Piquete).filter(Piquete.id == m.piquete_id).first()
        result.append({
            "id": m.id, "piquete_id": m.piquete_id,
            "piquete_nome": pq.nome if pq else "",
            "lote": m.lote, "qtd_animais": m.qtd_animais,
            "peso_medio_kg": m.peso_medio_kg, "ua_total": m.ua_total,
            "data_entrada": m.data_entrada, "data_saida": m.data_saida,
            "altura_entrada": m.altura_entrada, "altura_saida": m.altura_saida,
            "dias_ocupacao": m.dias_ocupacao, "dias_descanso": m.dias_descanso,
            "condicao_pasto": m.condicao_pasto,
            "ganho_total_kg": m.ganho_total_kg, "ganho_ha_kg": m.ganho_ha_kg,
            "obs": m.obs,
        })
    return result


@router.post("/manejo/entrada")
def registrar_entrada(body: dict, db: Session = Depends(get_db)):
    piquete_id = body.get("piquete_id")
    if not piquete_id:
        raise HTTPException(status_code=400, detail="piquete_id é obrigatório.")
    pq = db.query(Piquete).filter(Piquete.id == piquete_id).first()
    if not pq:
        raise HTTPException(status_code=404, detail="Piquete não encontrado.")

    lote_existente = db.query(LotePasto).filter(
        LotePasto.piquete_id == piquete_id, LotePasto.status == "ATIVO"
    ).first()
    if lote_existente:
        raise HTTPException(status_code=400, detail="Piquete já possui um lote ativo.")

    data_entrada = body.get("data_entrada", date.today().isoformat())
    peso_medio   = body.get("peso_medio_kg") or 0
    qtd_animais  = body.get("qtd_animais") or 0
    ua_total     = calcular_ua(peso_medio, qtd_animais)

    # Calcular dias de descanso desde última saída
    ultimo = (
        db.query(ManejoPastagem)
        .filter(ManejoPastagem.piquete_id == piquete_id,
                ManejoPastagem.data_saida.isnot(None))
        .order_by(ManejoPastagem.data_saida.desc())
        .first()
    )
    dias_descanso = 0
    if ultimo and ultimo.data_saida:
        try:
            d1 = date.fromisoformat(ultimo.data_saida)
            d2 = date.fromisoformat(data_entrada)
            dias_descanso = max(0, (d2 - d1).days)
        except Exception:
            pass

    previsao = ""
    if pq.dias_descanso_alvo:
        try:
            d_ent = date.fromisoformat(data_entrada)
            previsao = (d_ent + timedelta(days=pq.dias_descanso_alvo)).isoformat()
        except Exception:
            pass

    manejo = ManejoPastagem(
        data_entrada=data_entrada,
        piquete_id=piquete_id,
        lote=body.get("lote"),
        qtd_animais=qtd_animais,
        peso_medio_kg=peso_medio,
        ua_total=ua_total,
        altura_entrada=body.get("altura_entrada"),
        dias_descanso=dias_descanso,
        obs=body.get("obs"),
    )
    db.add(manejo)

    lote_pasto = LotePasto(
        data=data_entrada,
        lote=body.get("lote"),
        piquete_id=piquete_id,
        qtd_cabecas=qtd_animais,
        peso_medio_kg=peso_medio,
        categoria=body.get("categoria"),
        data_entrada=data_entrada,
        previsao_saida=previsao,
        status="ATIVO",
    )
    db.add(lote_pasto)

    pq.status = "OCUPADO"
    db.commit()
    db.refresh(manejo)
    return {"id": manejo.id, "ua_total": ua_total, "previsao_saida": previsao}


@router.post("/manejo/saida")
def registrar_saida(body: dict, db: Session = Depends(get_db)):
    manejo_id = body.get("manejo_id")
    if not manejo_id:
        raise HTTPException(status_code=400, detail="manejo_id é obrigatório.")
    manejo = db.query(ManejoPastagem).filter(ManejoPastagem.id == manejo_id).first()
    if not manejo:
        raise HTTPException(status_code=404, detail="Registro de manejo não encontrado.")
    if manejo.data_saida:
        raise HTTPException(status_code=400, detail="Saída já registrada para este manejo.")

    data_saida = body.get("data_saida", date.today().isoformat())
    dias_ocupacao = 0
    try:
        d1 = date.fromisoformat(manejo.data_entrada)
        d2 = date.fromisoformat(data_saida)
        dias_ocupacao = max(0, (d2 - d1).days)
    except Exception:
        pass

    # Calcular ganho cruzando com pesagens
    ganho_total_kg = 0.0
    if manejo.lote:
        animais_lote = db.query(Animal).filter(Animal.lote.ilike(manejo.lote)).all()
        brincos = [a.brinco for a in animais_lote]
        if brincos:
            from sqlalchemy import and_, or_
            pesagens = db.query(Pesagem).filter(
                Pesagem.brinco.in_(brincos),
                Pesagem.data_pesagem >= manejo.data_entrada,
                Pesagem.data_pesagem <= data_saida,
            ).all()
            ganho_total_kg = round(sum(p.ganho_kg or 0 for p in pesagens), 2)

    pq = db.query(Piquete).filter(Piquete.id == manejo.piquete_id).first()
    area_ha = pq.area_ha if pq and pq.area_ha else 1
    ganho_ha_kg = round(ganho_total_kg / area_ha, 2) if area_ha else 0.0

    manejo.data_saida     = data_saida
    manejo.altura_saida   = body.get("altura_saida")
    manejo.condicao_pasto = body.get("condicao_pasto")
    manejo.dias_ocupacao  = dias_ocupacao
    manejo.ganho_total_kg = ganho_total_kg
    manejo.ganho_ha_kg    = ganho_ha_kg
    manejo.obs            = body.get("obs") or manejo.obs

    lote_ativo = db.query(LotePasto).filter(
        LotePasto.piquete_id == manejo.piquete_id,
        LotePasto.status == "ATIVO",
    ).first()
    if lote_ativo:
        lote_ativo.status = "SAIU"

    if pq:
        pq.status = "EM_DESCANSO"

    db.commit()
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
    db: Session = Depends(get_db),
):
    q = db.query(AdubacaoPastagem)
    if piquete_id:
        q = q.filter(AdubacaoPastagem.piquete_id == piquete_id)
    if data_ini:
        q = q.filter(AdubacaoPastagem.data >= data_ini)
    if data_fim:
        q = q.filter(AdubacaoPastagem.data <= data_fim)
    rows = q.order_by(AdubacaoPastagem.data.desc()).all()
    result = []
    for a in rows:
        pq = db.query(Piquete).filter(Piquete.id == a.piquete_id).first()
        result.append({
            "id": a.id, "data": a.data, "piquete_id": a.piquete_id,
            "piquete_nome": pq.nome if pq else "",
            "produto": a.produto, "dose_kg_ha": a.dose_kg_ha,
            "custo_total": a.custo_total, "responsavel": a.responsavel, "obs": a.obs,
        })
    return result


@router.post("/adubacao")
def criar_adubacao(body: dict, db: Session = Depends(get_db)):
    if not body.get("piquete_id") or not body.get("produto"):
        raise HTTPException(status_code=400, detail="piquete_id e produto são obrigatórios.")
    a = AdubacaoPastagem(
        data=body.get("data", date.today().isoformat()),
        piquete_id=body["piquete_id"], produto=body["produto"],
        dose_kg_ha=body.get("dose_kg_ha"), custo_total=body.get("custo_total"),
        responsavel=body.get("responsavel"), obs=body.get("obs"),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "ok": True}


@router.put("/adubacao/{id}")
def editar_adubacao(id: int, body: dict, db: Session = Depends(get_db)):
    a = db.query(AdubacaoPastagem).filter(AdubacaoPastagem.id == id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Adubação não encontrada.")
    for campo in ["data", "piquete_id", "produto", "dose_kg_ha", "custo_total", "responsavel", "obs"]:
        if campo in body:
            setattr(a, campo, body[campo])
    db.commit()
    return {"id": a.id, "ok": True}


@router.delete("/adubacao/{id}")
def excluir_adubacao(id: int, db: Session = Depends(get_db)):
    a = db.query(AdubacaoPastagem).filter(AdubacaoPastagem.id == id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Adubação não encontrada.")
    db.delete(a)
    db.commit()
    return {"ok": True}


# ── CHUVA ─────────────────────────────────────────────────────────────

@router.get("/chuva")
def listar_chuva(
    data_ini: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    hoje = date.today()
    q = db.query(Chuva)
    if data_ini:
        q = q.filter(Chuva.data >= data_ini)
    if data_fim:
        q = q.filter(Chuva.data <= data_fim)
    rows = q.order_by(Chuva.data.desc()).all()

    mes_atual = hoje.strftime("%Y-%m")
    ano_atual = str(hoje.year)
    total_mes = sum(c.mm_chuva for c in rows if c.data and c.data[:7] == mes_atual)
    total_ano = sum(c.mm_chuva for c in rows if c.data and c.data[:4] == ano_atual)

    return {
        "registros": [{"id": c.id, "data": c.data, "area": c.area, "mm_chuva": c.mm_chuva, "obs": c.obs} for c in rows],
        "total_mes": round(total_mes, 1),
        "total_ano": round(total_ano, 1),
    }


@router.post("/chuva")
def criar_chuva(body: dict, db: Session = Depends(get_db)):
    if body.get("mm_chuva") is None:
        raise HTTPException(status_code=400, detail="mm_chuva é obrigatório.")
    c = Chuva(
        data=body.get("data", date.today().isoformat()),
        area=body.get("area", "Fazenda Geral"),
        mm_chuva=body["mm_chuva"], obs=body.get("obs"),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "ok": True}


@router.put("/chuva/{id}")
def editar_chuva(id: int, body: dict, db: Session = Depends(get_db)):
    c = db.query(Chuva).filter(Chuva.id == id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    for campo in ["data", "area", "mm_chuva", "obs"]:
        if campo in body:
            setattr(c, campo, body[campo])
    db.commit()
    return {"id": c.id, "ok": True}


@router.delete("/chuva/{id}")
def excluir_chuva(id: int, db: Session = Depends(get_db)):
    c = db.query(Chuva).filter(Chuva.id == id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ── DASHBOARD ─────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard_pastagem(db: Session = Depends(get_db)):
    hoje = date.today()
    piquetes = db.query(Piquete).all()

    semaforos = {"verde": 0, "amarelo": 0, "vermelho": 0,
                 "sair_agora": 0, "ocupado": 0, "sem_dados": 0}
    alertas = []
    taxa_lotacoes = []

    for pq in piquetes:
        s = semaforo_piquete(pq.id, db)
        cor = s["semaforo"].lower()
        if cor in semaforos:
            semaforos[cor] += 1

        if s["semaforo"] == "SAIR_AGORA":
            alertas.append({"tipo": "SAIR_AGORA", "piquete": pq.nome, "mensagem": s["mensagem"]})
        elif s["semaforo"] == "SEM_DADOS":
            alertas.append({"tipo": "SEM_DADOS", "piquete": pq.nome, "mensagem": s["mensagem"]})

        if s["semaforo"] == "OCUPADO" and pq.area_ha:
            lote = db.query(LotePasto).filter(
                LotePasto.piquete_id == pq.id, LotePasto.status == "ATIVO"
            ).first()
            if lote:
                ua = calcular_ua(lote.peso_medio_kg or 0, lote.qtd_cabecas or 0)
                taxa_lotacoes.append(calcular_taxa_lotacao(ua, pq.area_ha))

    taxa_lotacao_media = round(sum(taxa_lotacoes) / len(taxa_lotacoes), 2) if taxa_lotacoes else 0.0

    # Dias de descanso médio
    em_descanso = [pq for pq in piquetes if pq.status == "EM_DESCANSO"]
    dias_desc_lista = []
    for pq in em_descanso:
        s = semaforo_piquete(pq.id, db)
        if s["dias_descanso"]:
            dias_desc_lista.append(s["dias_descanso"])
    dias_descanso_medio = round(sum(dias_desc_lista) / len(dias_desc_lista)) if dias_desc_lista else 0

    # Ganho médio diário dos lotes ativos
    lotes_ativos = db.query(LotePasto).filter(LotePasto.status == "ATIVO").all()
    ganhos_dia = []
    for lote in lotes_ativos:
        if lote.lote and lote.data_entrada:
            animais = db.query(Animal).filter(Animal.lote.ilike(lote.lote)).all()
            brincos = [a.brinco for a in animais]
            if brincos:
                pesagens = db.query(Pesagem).filter(
                    Pesagem.brinco.in_(brincos),
                    Pesagem.data_pesagem >= lote.data_entrada,
                ).all()
                total_ganho = sum(p.ganho_kg or 0 for p in pesagens)
                try:
                    dias = (hoje - date.fromisoformat(lote.data_entrada)).days
                    if dias > 0:
                        ganhos_dia.append(total_ganho / dias)
                except Exception:
                    pass
    ganho_medio_diario_kg = round(sum(ganhos_dia) / len(ganhos_dia), 2) if ganhos_dia else 0.0

    # Custo adubação/ha (últimos 90 dias)
    d90 = (hoje - timedelta(days=90)).isoformat()
    adubs = db.query(AdubacaoPastagem).filter(AdubacaoPastagem.data >= d90).all()
    custo_total_adub = sum(a.custo_total or 0 for a in adubs)
    area_total = sum(pq.area_ha or 0 for pq in piquetes)
    custo_adubacao_ha = round(custo_total_adub / area_total, 2) if area_total else 0.0

    # Chuva mês e ano
    mes_atual = hoje.strftime("%Y-%m")
    ano_atual = str(hoje.year)
    chuvas_todas = db.query(Chuva).all()
    chuva_mes   = round(sum(c.mm_chuva for c in chuvas_todas if c.data and c.data[:7] == mes_atual), 1)
    chuva_ano   = round(sum(c.mm_chuva for c in chuvas_todas if c.data and c.data[:4] == ano_atual), 1)
    if chuva_mes < 50:
        alertas.append({"tipo": "SECA", "piquete": "Geral",
                        "mensagem": f"Apenas {chuva_mes} mm no mês. Risco de seca!"})

    # Ranking piquetes
    from sqlalchemy import desc as _desc
    ranking_rows = (
        db.query(
            ManejoPastagem.piquete_id,
            func.count(ManejoPastagem.id).label("ciclos"),
            func.avg(ManejoPastagem.ganho_ha_kg).label("ganho_medio"),
        )
        .filter(ManejoPastagem.data_saida.isnot(None))
        .group_by(ManejoPastagem.piquete_id)
        .order_by(_desc("ganho_medio"))
        .limit(5)
        .all()
    )
    ranking = []
    for row in ranking_rows:
        pq = db.query(Piquete).filter(Piquete.id == row.piquete_id).first()
        ranking.append({
            "nome": pq.nome if pq else str(row.piquete_id),
            "ganho_ha_kg": round(row.ganho_medio or 0, 2),
            "ciclos": row.ciclos,
        })

    # KPIs de lotes
    lotes_todos = db.query(Lote).filter(Lote.status == "ATIVO").all()
    lotes_em_piquete = [l for l in lotes_todos if l.piquete_id]
    ua_has_lotes = [l.ua_ha for l in lotes_em_piquete if l.ua_ha]
    lotes_criticos = sum(1 for l in lotes_todos if l.classificacao == "CRÍTICA")
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
def ranking_piquetes(db: Session = Depends(get_db)):
    from sqlalchemy import desc as _desc
    rows = (
        db.query(
            ManejoPastagem.piquete_id,
            func.count(ManejoPastagem.id).label("ciclos"),
            func.avg(ManejoPastagem.ganho_ha_kg).label("ganho_ha_medio"),
            func.avg(ManejoPastagem.ua_total).label("ua_media"),
        )
        .filter(ManejoPastagem.data_saida.isnot(None))
        .group_by(ManejoPastagem.piquete_id)
        .order_by(_desc("ganho_ha_medio"))
        .all()
    )
    result = []
    for row in rows:
        pq = db.query(Piquete).filter(Piquete.id == row.piquete_id).first()
        hoje = date.today()
        d90 = (hoje - timedelta(days=90)).isoformat()
        custo_adub = db.query(func.sum(AdubacaoPastagem.custo_total)).filter(
            AdubacaoPastagem.piquete_id == row.piquete_id,
            AdubacaoPastagem.data >= d90,
        ).scalar() or 0
        area = pq.area_ha if pq and pq.area_ha else 1
        result.append({
            "piquete": pq.nome if pq else str(row.piquete_id),
            "ciclos": row.ciclos,
            "ganho_ha_medio": round(row.ganho_ha_medio or 0, 2),
            "lotacao_media": round((row.ua_media or 0) / area, 2) if area else 0,
            "custo_adubacao_ha": round(custo_adub / area, 2),
        })
    return result


@router.get("/relatorios/chuva-mensal")
def chuva_mensal(db: Session = Depends(get_db)):
    hoje = date.today()
    resultado = {}
    for i in range(11, -1, -1):
        mes = hoje.month - i
        ano = hoje.year
        while mes <= 0:
            mes += 12
            ano -= 1
        chave = f"{ano}-{mes:02d}"
        total = db.query(func.sum(Chuva.mm_chuva)).filter(
            Chuva.data.like(f"{chave}%")
        ).scalar() or 0
        resultado[chave] = round(total, 1)
    return resultado


@router.get("/relatorios/adubacao-historico")
def adubacao_historico(db: Session = Depends(get_db)):
    rows = db.query(AdubacaoPastagem).order_by(AdubacaoPastagem.data.desc()).all()
    result = []
    for a in rows:
        pq = db.query(Piquete).filter(Piquete.id == a.piquete_id).first()
        result.append({
            "id": a.id, "piquete": pq.nome if pq else "", "data": a.data,
            "produto": a.produto, "dose_kg_ha": a.dose_kg_ha, "custo_total": a.custo_total,
        })
    return result


@router.get("/relatorios/comparativo")
def comparativo_piquetes(db: Session = Depends(get_db)):
    hoje = date.today()
    meses = []
    for i in range(5, -1, -1):
        mes = hoje.month - i
        ano = hoje.year
        while mes <= 0:
            mes += 12
            ano -= 1
        meses.append(f"{ano}-{mes:02d}")

    piquetes = db.query(Piquete).order_by(Piquete.nome).all()
    tabela = []
    for pq in piquetes:
        linha = {"piquete": pq.nome}
        for chave in meses:
            ganho = db.query(func.avg(ManejoPastagem.ganho_ha_kg)).filter(
                ManejoPastagem.piquete_id == pq.id,
                ManejoPastagem.data_entrada.like(f"{chave}%"),
                ManejoPastagem.data_saida.isnot(None),
            ).scalar()
            linha[chave] = round(ganho or 0, 2)
        tabela.append(linha)
    return {"meses": meses, "tabela": tabela}


# ── Helpers de Lotes ─────────────────────────────────────────────────────────

def _classificar_ua_ha(ua_ha: float | None) -> str:
    if ua_ha is None:
        return "SEM_DADOS"
    if ua_ha <= 1.5:
        return "LEVE"
    if ua_ha <= 3.0:
        return "IDEAL"
    if ua_ha <= 4.5:
        return "ALTA"
    return "CRITICA"


def _recalcular_lote(db: Session, lote: Lote):
    membros = db.query(LoteAnimal).filter_by(lote_id=lote.id, status="ATIVO").all()
    brincos = [m.brinco for m in membros]
    ua_total = 0.0
    for brinco in brincos:
        animal = db.query(Animal).filter_by(brinco=brinco).first()
        if animal and animal.peso_atual:
            ua_total += round(animal.peso_atual / 450, 3)
    lote.ua_total = round(ua_total, 2)

    if lote.piquete_id:
        pq = db.query(Piquete).filter_by(id=lote.piquete_id).first()
        if pq and pq.area_ha:
            lote.ua_ha = round(ua_total / pq.area_ha, 2)
        else:
            lote.ua_ha = None
    else:
        lote.ua_ha = None

    lote.classificacao = _classificar_ua_ha(lote.ua_ha)


def _lote_dict(db: Session, lote: Lote) -> dict:
    membros = db.query(LoteAnimal).filter_by(lote_id=lote.id, status="ATIVO").all()
    pq = db.query(Piquete).filter_by(id=lote.piquete_id).first() if lote.piquete_id else None
    return {
        "id": lote.id,
        "nome": lote.nome,
        "categoria": lote.categoria,
        "descricao": lote.descricao,
        "piquete_id": lote.piquete_id,
        "piquete_nome": pq.nome if pq else None,
        "status": lote.status,
        "ua_total": lote.ua_total,
        "ua_ha": lote.ua_ha,
        "classificacao": lote.classificacao,
        "qtd_animais": len(membros),
        "criado_em": lote.criado_em,
    }


# ── Endpoints de Lotes ───────────────────────────────────────────────────────

@router.get("/lotes/simular")
def simular_lotacao(
    piquete_id: int,
    brincos: str,
    db: Session = Depends(get_db),
):
    pq = db.query(Piquete).filter_by(id=piquete_id).first()
    if not pq:
        raise HTTPException(404, "Piquete não encontrado")

    lista = [b.strip() for b in brincos.split(",") if b.strip()]
    ua_total = 0.0
    for brinco in lista:
        a = db.query(Animal).filter_by(brinco=brinco).first()
        if a and a.peso_atual:
            ua_total += a.peso_atual / 450

    ua_ha = round(ua_total / pq.area_ha, 2) if pq.area_ha else None
    return {
        "piquete_id": piquete_id,
        "area_ha": pq.area_ha,
        "qtd_animais": len(lista),
        "ua_total": round(ua_total, 2),
        "ua_ha": ua_ha,
        "classificacao": _classificar_ua_ha(ua_ha),
    }


@router.get("/lotes")
def listar_lotes(db: Session = Depends(get_db)):
    lotes = db.query(Lote).order_by(Lote.nome).all()
    return [_lote_dict(db, lt) for lt in lotes]


@router.get("/lotes/{lote_id}")
def obter_lote(lote_id: int, db: Session = Depends(get_db)):
    lote = db.query(Lote).filter_by(id=lote_id).first()
    if not lote:
        raise HTTPException(404, "Lote não encontrado")
    return _lote_dict(db, lote)


@router.post("/lotes", status_code=201)
def criar_lote(payload: dict, db: Session = Depends(get_db)):
    if db.query(Lote).filter_by(nome=payload.get("nome")).first():
        raise HTTPException(400, "Já existe um lote com esse nome")
    lote = Lote(
        nome=payload["nome"],
        categoria=payload.get("categoria"),
        descricao=payload.get("descricao"),
        piquete_id=payload.get("piquete_id"),
        status=payload.get("status", "ATIVO"),
    )
    db.add(lote)
    db.flush()
    _recalcular_lote(db, lote)
    db.commit()
    db.refresh(lote)
    return _lote_dict(db, lote)


@router.put("/lotes/{lote_id}")
def atualizar_lote(lote_id: int, payload: dict, db: Session = Depends(get_db)):
    lote = db.query(Lote).filter_by(id=lote_id).first()
    if not lote:
        raise HTTPException(404, "Lote não encontrado")
    for campo in ("nome", "categoria", "descricao", "status"):
        if campo in payload:
            setattr(lote, campo, payload[campo])
    _recalcular_lote(db, lote)
    db.commit()
    db.refresh(lote)
    return _lote_dict(db, lote)


@router.delete("/lotes/{lote_id}")
def excluir_lote(lote_id: int, db: Session = Depends(get_db)):
    lote = db.query(Lote).filter_by(id=lote_id).first()
    if not lote:
        raise HTTPException(404, "Lote não encontrado")
    membros = db.query(LoteAnimal).filter_by(lote_id=lote_id, status="ATIVO").count()
    if membros > 0:
        raise HTTPException(400, "Remova os animais do lote antes de excluir")
    db.query(LoteAnimal).filter_by(lote_id=lote_id).delete()
    db.delete(lote)
    db.commit()
    return {"ok": True}


@router.get("/lotes/{lote_id}/animais")
def listar_animais_lote(lote_id: int, db: Session = Depends(get_db)):
    lote = db.query(Lote).filter_by(id=lote_id).first()
    if not lote:
        raise HTTPException(404, "Lote não encontrado")
    membros = db.query(LoteAnimal).filter_by(lote_id=lote_id, status="ATIVO").all()
    resultado = []
    for m in membros:
        a = db.query(Animal).filter_by(brinco=m.brinco).first()
        resultado.append({
            "brinco": m.brinco,
            "nome": a.nome if a else None,
            "tipo": a.tipo if a else None,
            "peso_atual": a.peso_atual if a else None,
            "ua": round((a.peso_atual or 0) / 450, 3) if a else 0,
            "data_entrada": m.data_entrada,
        })
    return resultado


@router.post("/lotes/{lote_id}/animais")
def adicionar_animal_lote(lote_id: int, payload: dict, db: Session = Depends(get_db)):
    lote = db.query(Lote).filter_by(id=lote_id).first()
    if not lote:
        raise HTTPException(404, "Lote não encontrado")
    brinco = payload.get("brinco", "").strip().upper()
    if not brinco:
        raise HTTPException(400, "brinco obrigatório")
    animal = db.query(Animal).filter_by(brinco=brinco).first()
    if not animal:
        raise HTTPException(404, f"Animal {brinco} não encontrado")
    existente = db.query(LoteAnimal).filter_by(lote_id=lote_id, brinco=brinco, status="ATIVO").first()
    if existente:
        raise HTTPException(400, "Animal já está neste lote")
    db.add(LoteAnimal(
        lote_id=lote_id,
        brinco=brinco,
        data_entrada=payload.get("data_entrada", date.today().strftime("%Y-%m-%d")),
        status="ATIVO",
    ))
    db.flush()
    _recalcular_lote(db, lote)
    db.commit()
    return _lote_dict(db, lote)


@router.delete("/lotes/{lote_id}/animais/{brinco}")
def remover_animal_lote(lote_id: int, brinco: str, db: Session = Depends(get_db)):
    lote = db.query(Lote).filter_by(id=lote_id).first()
    if not lote:
        raise HTTPException(404, "Lote não encontrado")
    membro = db.query(LoteAnimal).filter_by(lote_id=lote_id, brinco=brinco.upper(), status="ATIVO").first()
    if not membro:
        raise HTTPException(404, "Animal não encontrado no lote")
    membro.status = "SAIU"
    membro.data_saida = date.today().strftime("%Y-%m-%d")
    db.flush()
    _recalcular_lote(db, lote)
    db.commit()
    return _lote_dict(db, lote)


@router.post("/lotes/{lote_id}/alocar")
def alocar_lote_piquete(lote_id: int, payload: dict, db: Session = Depends(get_db)):
    lote = db.query(Lote).filter_by(id=lote_id).first()
    if not lote:
        raise HTTPException(404, "Lote não encontrado")
    piquete_id = payload.get("piquete_id")
    pq = db.query(Piquete).filter_by(id=piquete_id).first()
    if not pq:
        raise HTTPException(404, "Piquete não encontrado")
    lote.piquete_id = piquete_id
    _recalcular_lote(db, lote)
    db.commit()
    return _lote_dict(db, lote)


@router.post("/lotes/{lote_id}/desalocar")
def desalocar_lote_piquete(lote_id: int, db: Session = Depends(get_db)):
    lote = db.query(Lote).filter_by(id=lote_id).first()
    if not lote:
        raise HTTPException(404, "Lote não encontrado")
    lote.piquete_id = None
    lote.ua_ha = None
    lote.classificacao = _classificar_ua_ha(None)
    db.commit()
    return _lote_dict(db, lote)
