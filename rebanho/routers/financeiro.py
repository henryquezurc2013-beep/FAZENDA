from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Compra, Despesa, Venda
from schemas import CompraCreate, CompraOut, DespesaCreate, DespesaOut, VendaCreate, VendaOut

router_compras = APIRouter()
router_vendas = APIRouter()
router_despesas = APIRouter()


def _parse_data(valor: str, campo: str) -> date:
    try:
        return date.fromisoformat(valor)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"{campo} inválida, use YYYY-MM-DD")


# ─── COMPRAS ─────────────────────────────────────────────────────────────────

@router_compras.get("", response_model=List[CompraOut])
def listar_compras(
    fornecedor: Optional[str] = Query(None),
    mes: Optional[int] = Query(None),
    ano: Optional[int] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Compra)
    if fornecedor:
        q = q.filter(Compra.fornecedor.ilike(f"%{fornecedor}%"))
    if mes:
        q = q.filter(Compra.mes == mes)
    if ano:
        q = q.filter(Compra.ano == ano)
    if data_inicio:
        q = q.filter(Compra.data >= data_inicio)
    if data_fim:
        q = q.filter(Compra.data <= data_fim)
    return q.order_by(Compra.data.desc()).all()


@router_compras.post("", response_model=CompraOut, status_code=201)
def criar_compra(payload: CompraCreate, db: Session = Depends(get_db)):
    missing = [f for f in ("fornecedor", "data", "valor_unit", "quantidade") if not getattr(payload, f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")

    dt = _parse_data(payload.data, "data")
    valor_total = round((payload.valor_unit or 0) * (payload.quantidade or 1), 2)

    compra = Compra(
        **{k: v for k, v in payload.model_dump().items()},
        valor_total=valor_total,
        mes=dt.month,
        ano=dt.year,
    )
    db.add(compra)
    db.commit()
    db.refresh(compra)
    return compra


@router_compras.put("/{id}", response_model=CompraOut)
def atualizar_compra(id: int, payload: CompraCreate, db: Session = Depends(get_db)):
    compra = db.query(Compra).filter(Compra.id == id).first()
    if not compra:
        raise HTTPException(status_code=404, detail="Compra não encontrada")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(compra, k, v)

    compra.valor_total = round((compra.valor_unit or 0) * (compra.quantidade or 1), 2)
    if compra.data:
        dt = _parse_data(compra.data, "data")
        compra.mes = dt.month
        compra.ano = dt.year

    db.commit()
    db.refresh(compra)
    return compra


@router_compras.delete("/{id}")
def deletar_compra(id: int, db: Session = Depends(get_db)):
    compra = db.query(Compra).filter(Compra.id == id).first()
    if not compra:
        raise HTTPException(status_code=404, detail="Compra não encontrada")
    db.delete(compra)
    db.commit()
    return {"mensagem": "Compra removida com sucesso"}


# ─── VENDAS ──────────────────────────────────────────────────────────────────

@router_vendas.get("", response_model=List[VendaOut])
def listar_vendas(
    cliente: Optional[str] = Query(None),
    mes: Optional[int] = Query(None),
    ano: Optional[int] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Venda)
    if cliente:
        q = q.filter(Venda.cliente.ilike(f"%{cliente}%"))
    if mes:
        q = q.filter(Venda.mes == mes)
    if ano:
        q = q.filter(Venda.ano == ano)
    if data_inicio:
        q = q.filter(Venda.data >= data_inicio)
    if data_fim:
        q = q.filter(Venda.data <= data_fim)
    return q.order_by(Venda.data.desc()).all()


@router_vendas.post("", response_model=VendaOut, status_code=201)
def criar_venda(payload: VendaCreate, db: Session = Depends(get_db)):
    missing = [f for f in ("cliente", "data", "valor_unit", "quantidade") if not getattr(payload, f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")

    dt = _parse_data(payload.data, "data")
    valor_total = round((payload.valor_unit or 0) * (payload.quantidade or 1), 2)

    venda = Venda(
        **{k: v for k, v in payload.model_dump().items()},
        valor_total=valor_total,
        mes=dt.month,
        ano=dt.year,
    )
    db.add(venda)
    db.commit()
    db.refresh(venda)
    return venda


@router_vendas.put("/{id}", response_model=VendaOut)
def atualizar_venda(id: int, payload: VendaCreate, db: Session = Depends(get_db)):
    venda = db.query(Venda).filter(Venda.id == id).first()
    if not venda:
        raise HTTPException(status_code=404, detail="Venda não encontrada")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(venda, k, v)

    venda.valor_total = round((venda.valor_unit or 0) * (venda.quantidade or 1), 2)
    if venda.data:
        dt = _parse_data(venda.data, "data")
        venda.mes = dt.month
        venda.ano = dt.year

    db.commit()
    db.refresh(venda)
    return venda


@router_vendas.delete("/{id}")
def deletar_venda(id: int, db: Session = Depends(get_db)):
    venda = db.query(Venda).filter(Venda.id == id).first()
    if not venda:
        raise HTTPException(status_code=404, detail="Venda não encontrada")
    db.delete(venda)
    db.commit()
    return {"mensagem": "Venda removida com sucesso"}


# ─── DESPESAS ────────────────────────────────────────────────────────────────

def _despesa_out(d: Despesa) -> Dict[str, Any]:
    hoje = date.today().isoformat()
    vencida = bool(
        d.vencimento and d.vencimento < hoje and (d.status or "").upper() == "PENDENTE"
    )
    row = {c.name: getattr(d, c.name) for c in d.__table__.columns}
    row["vencida"] = vencida
    return row


@router_despesas.get("")
def listar_despesas(
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    mes: Optional[int] = Query(None),
    ano: Optional[int] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Despesa)
    if tipo:
        q = q.filter(Despesa.tipo.ilike(tipo))
    if status:
        q = q.filter(Despesa.status.ilike(status))
    if mes:
        q = q.filter(Despesa.mes == mes)
    if ano:
        q = q.filter(Despesa.ano == ano)
    if data_inicio:
        q = q.filter(Despesa.vencimento >= data_inicio)
    if data_fim:
        q = q.filter(Despesa.vencimento <= data_fim)
    return [_despesa_out(d) for d in q.order_by(Despesa.vencimento.desc()).all()]


@router_despesas.post("", status_code=201)
def criar_despesa(payload: DespesaCreate, db: Session = Depends(get_db)):
    missing = [f for f in ("valor", "vencimento") if not getattr(payload, f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")

    dt = _parse_data(payload.vencimento, "vencimento")
    data = payload.model_dump()
    if not data.get("status"):
        data["status"] = "PENDENTE"

    despesa = Despesa(**data, mes=dt.month, ano=dt.year)
    db.add(despesa)
    db.commit()
    db.refresh(despesa)
    return _despesa_out(despesa)


@router_despesas.put("/{id}")
def atualizar_despesa(id: int, payload: DespesaCreate, db: Session = Depends(get_db)):
    despesa = db.query(Despesa).filter(Despesa.id == id).first()
    if not despesa:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(despesa, k, v)

    if despesa.vencimento:
        dt = _parse_data(despesa.vencimento, "vencimento")
        despesa.mes = dt.month
        despesa.ano = dt.year

    db.commit()
    db.refresh(despesa)
    return _despesa_out(despesa)


@router_despesas.delete("/{id}")
def deletar_despesa(id: int, db: Session = Depends(get_db)):
    despesa = db.query(Despesa).filter(Despesa.id == id).first()
    if not despesa:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    db.delete(despesa)
    db.commit()
    return {"mensagem": "Despesa removida com sucesso"}
