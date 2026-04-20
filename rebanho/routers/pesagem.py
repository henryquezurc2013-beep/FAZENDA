from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date

from database import get_db
from models import Animal, Pesagem
from schemas import PesagemCreate, PesagemOut

router = APIRouter()


@router.get("", response_model=List[PesagemOut])
def listar_pesagens(
    brinco: Optional[str] = Query(None),
    mes: Optional[int] = Query(None),
    ano: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Pesagem)
    if brinco:
        q = q.filter(Pesagem.brinco.ilike(brinco))
    if mes:
        q = q.filter(Pesagem.mes == mes)
    if ano:
        q = q.filter(Pesagem.ano == ano)
    return q.order_by(Pesagem.data_pesagem.desc()).all()


@router.post("", response_model=PesagemOut, status_code=201)
def criar_pesagem(payload: PesagemCreate, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.brinco.ilike(payload.brinco)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")

    try:
        dt_atual = date.fromisoformat(payload.data_pesagem)
    except ValueError:
        raise HTTPException(status_code=400, detail="data_pesagem inválida, use YYYY-MM-DD")

    anterior = (
        db.query(Pesagem)
        .filter(Pesagem.brinco.ilike(payload.brinco))
        .filter(Pesagem.data_pesagem < payload.data_pesagem)
        .order_by(Pesagem.data_pesagem.desc())
        .first()
    )

    ganho_kg = 0.0
    ganho_pct = 0.0
    media_dia_kg = 0.0

    if anterior:
        ganho_kg = round(payload.peso - anterior.peso, 2)
        if anterior.peso:
            ganho_pct = round((ganho_kg / anterior.peso) * 100, 1)
        try:
            dt_anterior = date.fromisoformat(anterior.data_pesagem)
            dias = (dt_atual - dt_anterior).days
            if dias > 0:
                media_dia_kg = round(ganho_kg / dias, 1)
        except Exception:
            pass

    pesagem = Pesagem(
        brinco=payload.brinco,
        data_pesagem=payload.data_pesagem,
        peso=payload.peso,
        ganho_kg=ganho_kg,
        ganho_pct=ganho_pct,
        media_dia_kg=media_dia_kg,
        mes=dt_atual.month,
        ano=dt_atual.year,
        pasto=payload.pasto or animal.pasto,
    )
    db.add(pesagem)

    animal.peso_atual = payload.peso
    if animal.valor_compra and animal.valor_compra > 0 and payload.peso > 0:
        animal.custo_kg = round(animal.valor_compra / payload.peso, 2)
        animal.custo_arroba = round(animal.valor_compra / (payload.peso / 15), 2)
    db.add(animal)

    db.commit()
    db.refresh(pesagem)
    return pesagem


@router.put("/{id}", response_model=PesagemOut)
def atualizar_pesagem(id: int, payload: PesagemCreate, db: Session = Depends(get_db)):
    pesagem = db.query(Pesagem).filter(Pesagem.id == id).first()
    if not pesagem:
        raise HTTPException(status_code=404, detail="Pesagem não encontrada")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(pesagem, k, v)

    db.commit()
    db.refresh(pesagem)
    return pesagem


@router.delete("/{id}")
def deletar_pesagem(id: int, db: Session = Depends(get_db)):
    pesagem = db.query(Pesagem).filter(Pesagem.id == id).first()
    if not pesagem:
        raise HTTPException(status_code=404, detail="Pesagem não encontrada")
    db.delete(pesagem)
    db.commit()
    return {"mensagem": "Pesagem removida com sucesso"}
