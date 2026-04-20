from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import (
    EstoqueSuplemento, LancamentoRacao, Lote, LoteAnimal,
    Pesagem, PlanoNutricional, Suplemento,
)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class SuplementoIn(BaseModel):
    nome: str
    tipo: str
    fabricante: Optional[str] = None
    preco_kg: float
    pct_min: Optional[float] = None
    pct_max: Optional[float] = None
    g_min_fixo: Optional[float] = None
    g_max_fixo: Optional[float] = None
    objetivo: Optional[str] = None
    obs: Optional[str] = None

class PlanoIn(BaseModel):
    lote_id: int
    suplemento_id: int
    data_inicio: str
    data_fim: Optional[str] = None
    qtd_animais: int
    peso_medio_kg: float
    obs: Optional[str] = None

class LancamentoIn(BaseModel):
    plano_id: int
    lote_id: int
    suplemento_id: int
    data: str
    qtd_fornecida_kg: float
    qtd_planejada_kg: Optional[float] = None
    responsavel: Optional[str] = None
    obs: Optional[str] = None

class EstoqueIn(BaseModel):
    suplemento_id: int
    data: str
    tipo_mov: str          # ENTRADA | SAIDA | AJUSTE
    quantidade_kg: float
    preco_kg: Optional[float] = None
    fornecedor: Optional[str] = None
    nf: Optional[str] = None
    obs: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _calc_consumo(sup: Suplemento, peso_medio_kg: float, qtd_animais: int):
    if sup.pct_min is not None and sup.pct_max is not None:
        g_min = sup.pct_min / 100 * peso_medio_kg * 1000
        g_max = sup.pct_max / 100 * peso_medio_kg * 1000
    else:
        g_min = sup.g_min_fixo or 0
        g_max = sup.g_max_fixo or g_min
    g_med = (g_min + g_max) / 2
    return g_min, g_max, g_med

def _custo_estimado(g_med: float, qtd_animais: int, preco_kg: float):
    consumo_kg_dia = g_med / 1000 * qtd_animais
    custo_dia = consumo_kg_dia * preco_kg
    custo_mes = custo_dia * 30
    return custo_dia, custo_mes

def _saldo_estoque(db: Session, suplemento_id: int) -> float:
    rows = db.query(EstoqueSuplemento).filter(
        EstoqueSuplemento.suplemento_id == suplemento_id
    ).all()
    saldo = 0.0
    for r in rows:
        if r.tipo_mov in ("ENTRADA", "AJUSTE"):
            saldo += r.quantidade_kg
        else:
            saldo -= r.quantidade_kg
    return round(saldo, 3)


# ── Suplementos ───────────────────────────────────────────────────────────────

@router.get("/suplementos")
def listar_suplementos(db: Session = Depends(get_db)):
    rows = db.query(Suplemento).order_by(Suplemento.nome).all()
    result = []
    for s in rows:
        saldo = _saldo_estoque(db, s.id)
        consumo_medio_dia = _consumo_medio_diario(db, s.id)
        if consumo_medio_dia and consumo_medio_dia > 0:
            dias_restantes = saldo / consumo_medio_dia
            if dias_restantes < 7:
                situacao_estoque = "CRITICO"
            elif dias_restantes < 15:
                situacao_estoque = "BAIXO"
            else:
                situacao_estoque = "OK"
        else:
            dias_restantes = None
            situacao_estoque = "SEM_DADOS"
        result.append({
            "id": s.id, "nome": s.nome, "tipo": s.tipo,
            "fabricante": s.fabricante, "preco_kg": s.preco_kg,
            "pct_min": s.pct_min, "pct_max": s.pct_max,
            "g_min_fixo": s.g_min_fixo, "g_max_fixo": s.g_max_fixo,
            "objetivo": s.objetivo, "ativo": s.ativo, "obs": s.obs,
            "saldo_kg": saldo, "dias_restantes": dias_restantes,
            "situacao_estoque": situacao_estoque,
        })
    return result

@router.post("/suplementos")
def criar_suplemento(body: SuplementoIn, db: Session = Depends(get_db)):
    s = Suplemento(**body.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "ok": True}

@router.put("/suplementos/{sid}")
def editar_suplemento(sid: int, body: SuplementoIn, db: Session = Depends(get_db)):
    s = db.query(Suplemento).filter(Suplemento.id == sid).first()
    if not s:
        raise HTTPException(404, "Suplemento não encontrado")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return {"ok": True}

@router.delete("/suplementos/{sid}")
def excluir_suplemento(sid: int, db: Session = Depends(get_db)):
    s = db.query(Suplemento).filter(Suplemento.id == sid).first()
    if not s:
        raise HTTPException(404, "Suplemento não encontrado")
    db.delete(s); db.commit()
    return {"ok": True}


# ── Planos Nutricionais ───────────────────────────────────────────────────────

@router.get("/planos")
def listar_planos(db: Session = Depends(get_db)):
    planos = db.query(PlanoNutricional).order_by(PlanoNutricional.data_inicio.desc()).all()
    result = []
    for p in planos:
        sup = db.query(Suplemento).filter(Suplemento.id == p.suplemento_id).first()
        lote = db.query(Lote).filter(Lote.id == p.lote_id).first()
        result.append({
            "id": p.id, "lote_id": p.lote_id,
            "lote_nome": lote.nome if lote else "—",
            "suplemento_id": p.suplemento_id,
            "suplemento_nome": sup.nome if sup else "—",
            "data_inicio": p.data_inicio, "data_fim": p.data_fim,
            "qtd_animais": p.qtd_animais, "peso_medio_kg": p.peso_medio_kg,
            "preco_kg_snap": p.preco_kg_snap,
            "consumo_min_g": p.consumo_min_g, "consumo_max_g": p.consumo_max_g,
            "consumo_med_g": p.consumo_med_g,
            "custo_dia_est": p.custo_dia_est, "custo_mes_est": p.custo_mes_est,
            "status": p.status, "obs": p.obs,
        })
    return result

@router.post("/planos")
def criar_plano(body: PlanoIn, db: Session = Depends(get_db)):
    sup = db.query(Suplemento).filter(Suplemento.id == body.suplemento_id).first()
    if not sup:
        raise HTTPException(404, "Suplemento não encontrado")
    g_min, g_max, g_med = _calc_consumo(sup, body.peso_medio_kg, body.qtd_animais)
    custo_dia, custo_mes = _custo_estimado(g_med, body.qtd_animais, sup.preco_kg)
    p = PlanoNutricional(
        lote_id=body.lote_id, suplemento_id=body.suplemento_id,
        data_inicio=body.data_inicio, data_fim=body.data_fim,
        qtd_animais=body.qtd_animais, peso_medio_kg=body.peso_medio_kg,
        preco_kg_snap=sup.preco_kg,
        consumo_min_g=round(g_min, 1), consumo_max_g=round(g_max, 1),
        consumo_med_g=round(g_med, 1),
        custo_dia_est=round(custo_dia, 2), custo_mes_est=round(custo_mes, 2),
        obs=body.obs,
    )
    db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id, "ok": True}

@router.delete("/planos/{pid}")
def excluir_plano(pid: int, db: Session = Depends(get_db)):
    p = db.query(PlanoNutricional).filter(PlanoNutricional.id == pid).first()
    if not p:
        raise HTTPException(404, "Plano não encontrado")
    db.delete(p); db.commit()
    return {"ok": True}


# ── Lançamentos de Ração ──────────────────────────────────────────────────────

@router.get("/lancamentos")
def listar_lancamentos(
    lote_id: Optional[int] = None,
    data_ini: Optional[str] = None,
    data_fim: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(LancamentoRacao)
    if lote_id:
        q = q.filter(LancamentoRacao.lote_id == lote_id)
    if data_ini:
        q = q.filter(LancamentoRacao.data >= data_ini)
    if data_fim:
        q = q.filter(LancamentoRacao.data <= data_fim)
    rows = q.order_by(LancamentoRacao.data.desc()).all()
    result = []
    for r in rows:
        sup = db.query(Suplemento).filter(Suplemento.id == r.suplemento_id).first()
        lote = db.query(Lote).filter(Lote.id == r.lote_id).first()
        result.append({
            "id": r.id, "plano_id": r.plano_id,
            "lote_id": r.lote_id, "lote_nome": lote.nome if lote else "—",
            "suplemento_id": r.suplemento_id,
            "suplemento_nome": sup.nome if sup else "—",
            "data": r.data, "qtd_fornecida_kg": r.qtd_fornecida_kg,
            "qtd_planejada_kg": r.qtd_planejada_kg,
            "diferenca_kg": r.diferenca_kg, "custo_real": r.custo_real,
            "responsavel": r.responsavel, "obs": r.obs,
        })
    return result

@router.post("/lancamentos")
def criar_lancamento(body: LancamentoIn, db: Session = Depends(get_db)):
    sup = db.query(Suplemento).filter(Suplemento.id == body.suplemento_id).first()
    diferenca = None
    custo_real = None
    if body.qtd_planejada_kg is not None:
        diferenca = round(body.qtd_fornecida_kg - body.qtd_planejada_kg, 3)
    if sup:
        custo_real = round(body.qtd_fornecida_kg * sup.preco_kg, 2)
    l = LancamentoRacao(
        plano_id=body.plano_id, lote_id=body.lote_id,
        suplemento_id=body.suplemento_id, data=body.data,
        qtd_fornecida_kg=body.qtd_fornecida_kg,
        qtd_planejada_kg=body.qtd_planejada_kg,
        diferenca_kg=diferenca, custo_real=custo_real,
        responsavel=body.responsavel, obs=body.obs,
    )
    db.add(l)
    # descontar do estoque
    mov = EstoqueSuplemento(
        suplemento_id=body.suplemento_id,
        data=body.data, tipo_mov="SAIDA",
        quantidade_kg=body.qtd_fornecida_kg,
        preco_kg=sup.preco_kg if sup else None,
        valor_total=custo_real,
        obs=f"Lançamento automático lote {body.lote_id}",
    )
    db.add(mov)
    db.commit(); db.refresh(l)
    return {"id": l.id, "ok": True}

@router.delete("/lancamentos/{lid}")
def excluir_lancamento(lid: int, db: Session = Depends(get_db)):
    l = db.query(LancamentoRacao).filter(LancamentoRacao.id == lid).first()
    if not l:
        raise HTTPException(404, "Lançamento não encontrado")
    db.delete(l); db.commit()
    return {"ok": True}


# ── Estoque ───────────────────────────────────────────────────────────────────

@router.get("/estoque")
def listar_estoque(db: Session = Depends(get_db)):
    suplementos = db.query(Suplemento).filter(Suplemento.ativo == True).all()
    result = []
    for s in suplementos:
        saldo = _saldo_estoque(db, s.id)
        consumo_medio_dia = _consumo_medio_diario(db, s.id)
        if consumo_medio_dia and consumo_medio_dia > 0:
            dias_restantes = round(saldo / consumo_medio_dia, 1)
            if dias_restantes < 7:
                situacao = "CRITICO"
            elif dias_restantes < 15:
                situacao = "BAIXO"
            else:
                situacao = "OK"
        else:
            dias_restantes = None
            situacao = "SEM_DADOS"
        result.append({
            "suplemento_id": s.id, "nome": s.nome, "tipo": s.tipo,
            "saldo_kg": saldo, "preco_kg": s.preco_kg,
            "valor_estoque": round(saldo * s.preco_kg, 2),
            "consumo_medio_dia_kg": consumo_medio_dia,
            "dias_restantes": dias_restantes, "situacao": situacao,
        })
    return result

@router.post("/estoque/movimento")
def registrar_movimento(body: EstoqueIn, db: Session = Depends(get_db)):
    vt = None
    if body.preco_kg is not None:
        vt = round(body.quantidade_kg * body.preco_kg, 2)
    e = EstoqueSuplemento(
        suplemento_id=body.suplemento_id, data=body.data,
        tipo_mov=body.tipo_mov, quantidade_kg=body.quantidade_kg,
        preco_kg=body.preco_kg, valor_total=vt,
        fornecedor=body.fornecedor, nf=body.nf, obs=body.obs,
    )
    db.add(e); db.commit(); db.refresh(e)
    return {"id": e.id, "ok": True}

@router.get("/estoque/historico/{suplemento_id}")
def historico_estoque(suplemento_id: int, db: Session = Depends(get_db)):
    rows = db.query(EstoqueSuplemento).filter(
        EstoqueSuplemento.suplemento_id == suplemento_id
    ).order_by(EstoqueSuplemento.data.desc()).all()
    saldo_acum = 0.0
    result = []
    for r in reversed(rows):
        if r.tipo_mov in ("ENTRADA", "AJUSTE"):
            saldo_acum += r.quantidade_kg
        else:
            saldo_acum -= r.quantidade_kg
        result.insert(0, {
            "id": r.id, "data": r.data, "tipo_mov": r.tipo_mov,
            "quantidade_kg": r.quantidade_kg, "preco_kg": r.preco_kg,
            "valor_total": r.valor_total, "fornecedor": r.fornecedor,
            "nf": r.nf, "obs": r.obs,
            "saldo_acumulado": round(saldo_acum, 3),
        })
    return result


# ── Relatórios ────────────────────────────────────────────────────────────────

def _consumo_medio_diario(db: Session, suplemento_id: int, dias: int = 30) -> Optional[float]:
    from datetime import timedelta
    data_ini = (date.today() - timedelta(days=dias)).isoformat()
    rows = db.query(LancamentoRacao).filter(
        LancamentoRacao.suplemento_id == suplemento_id,
        LancamentoRacao.data >= data_ini,
    ).all()
    if not rows:
        return None
    total_kg = sum(r.qtd_fornecida_kg for r in rows)
    dias_distintos = len(set(r.data for r in rows))
    return round(total_kg / max(dias_distintos, 1), 3)

@router.get("/relatorios/ca")
def relatorio_ca(
    lote_id: Optional[int] = None,
    data_ini: Optional[str] = None,
    data_fim: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from datetime import timedelta
    if not data_ini:
        data_ini = (date.today() - timedelta(days=90)).isoformat()
    if not data_fim:
        data_fim = date.today().isoformat()

    q = db.query(LancamentoRacao).filter(
        LancamentoRacao.data >= data_ini,
        LancamentoRacao.data <= data_fim,
    )
    if lote_id:
        q = q.filter(LancamentoRacao.lote_id == lote_id)

    lancamentos = q.all()
    lotes_ids = list(set(l.lote_id for l in lancamentos))
    result = []
    for lid in lotes_ids:
        lote = db.query(Lote).filter(Lote.id == lid).first()
        pes = db.query(Pesagem).filter(
            Pesagem.data_pesagem >= data_ini,
            Pesagem.data_pesagem <= data_fim,
        ).all()
        lote_brincos = db.query(LoteAnimal).filter(
            LoteAnimal.lote_id == lid,
            LoteAnimal.status == "ATIVO",
        ).all()
        brincos = [la.brinco for la in lote_brincos]
        pesos_lote = [p for p in pes if p.brinco in brincos]

        consumo_total_kg = sum(l.qtd_fornecida_kg for l in lancamentos if l.lote_id == lid)
        if pesos_lote:
            ganho_total_kg = sum(p.ganho_kg for p in pesos_lote if p.ganho_kg and p.ganho_kg > 0)
            ca = round(consumo_total_kg / ganho_total_kg, 2) if ganho_total_kg > 0 else None
        else:
            ganho_total_kg = None
            ca = None

        if ca is None:
            ca_class = "SEM_DADOS"
        elif ca < 6:
            ca_class = "EXCELENTE"
        elif ca < 8:
            ca_class = "BOM"
        elif ca < 12:
            ca_class = "REGULAR"
        else:
            ca_class = "RUIM"

        result.append({
            "lote_id": lid,
            "lote_nome": lote.nome if lote else "—",
            "consumo_total_kg": round(consumo_total_kg, 2),
            "ganho_total_kg": round(ganho_total_kg, 2) if ganho_total_kg else None,
            "ca": ca, "ca_classificacao": ca_class,
        })
    return result

@router.get("/relatorios/custo-mensal")
def custo_mensal(db: Session = Depends(get_db)):
    from datetime import timedelta
    data_ini = (date.today() - timedelta(days=365)).isoformat()
    rows = db.query(LancamentoRacao).filter(LancamentoRacao.data >= data_ini).all()
    mensal: dict = {}
    for r in rows:
        mes = r.data[:7]
        mensal[mes] = mensal.get(mes, 0) + (r.custo_real or 0)
    return [{"mes": k, "custo": round(v, 2)} for k, v in sorted(mensal.items())]

@router.get("/relatorios/resumo")
def resumo_nutricao(db: Session = Depends(get_db)):
    from datetime import timedelta
    hoje = date.today().isoformat()
    mes_ini = hoje[:7] + "-01"

    planos_ativos = db.query(PlanoNutricional).filter(
        PlanoNutricional.status == "ATIVO"
    ).count()

    custo_mes = db.query(func.sum(LancamentoRacao.custo_real)).filter(
        LancamentoRacao.data >= mes_ini
    ).scalar() or 0

    suplementos = db.query(Suplemento).filter(Suplemento.ativo == True).all()
    criticos = 0
    for s in suplementos:
        saldo = _saldo_estoque(db, s.id)
        cmd = _consumo_medio_diario(db, s.id)
        if cmd and cmd > 0 and (saldo / cmd) < 7:
            criticos += 1

    return {
        "planos_ativos": planos_ativos,
        "custo_mes": round(custo_mes, 2),
        "estoque_critico": criticos,
        "total_suplementos": len(suplementos),
    }


# ── Seed ──────────────────────────────────────────────────────────────────────

def seed_nutricao(db: Session):
    if db.query(Suplemento).first():
        return
    suplementos = [
        Suplemento(
            nome="Sal Mineral Premium", tipo="MINERAL",
            fabricante="Tortuga", preco_kg=4.50,
            g_min_fixo=60, g_max_fixo=80,
            objetivo="Reposição mineral base",
        ),
        Suplemento(
            nome="Proteinado 30%", tipo="PROTEICO",
            fabricante="Agromix", preco_kg=3.80,
            pct_min=0.05, pct_max=0.08,
            objetivo="Ganho de peso na seca",
        ),
        Suplemento(
            nome="Sal Energético", tipo="ENERGETICO",
            fabricante="Nutripec", preco_kg=2.90,
            g_min_fixo=80, g_max_fixo=120,
            objetivo="Suplementação energética",
        ),
    ]
    for s in suplementos:
        db.add(s)
    db.commit()
