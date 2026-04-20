from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Config

router = APIRouter()


@router.get("")
def get_config(db: Session = Depends(get_db)):
    rows = db.query(Config).all()
    return {r.chave: r.valor for r in rows}


@router.put("/{chave}")
def set_config(chave: str, valor: str = Query(...), db: Session = Depends(get_db)):
    row = db.query(Config).filter_by(chave=chave).first()
    if row:
        row.valor = valor
    else:
        db.add(Config(chave=chave, valor=valor))
    db.commit()
    return {"chave": chave, "valor": valor}
