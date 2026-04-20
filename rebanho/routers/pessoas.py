import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Pessoa
from schemas import PessoaCreate, PessoaOut

router = APIRouter()

_PREFIXO = {"CLIENTE": "CLI", "FORNECEDOR": "FOR"}


def _gerar_codigo(tipo: str, db: Session) -> str:
    prefixo = _PREFIXO.get(tipo.upper())
    if not prefixo:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: {tipo}")

    existentes = (
        db.query(Pessoa.codigo)
        .filter(Pessoa.tipo.ilike(tipo), Pessoa.codigo.isnot(None))
        .all()
    )

    maior = 0
    for (codigo,) in existentes:
        m = re.match(rf"^{prefixo}-(\d+)$", codigo or "", re.IGNORECASE)
        if m:
            maior = max(maior, int(m.group(1)))

    novo = f"{prefixo}-{str(maior + 1).zfill(3)}"

    conflito = db.query(Pessoa).filter(Pessoa.codigo == novo).first()
    if conflito:
        raise HTTPException(status_code=500, detail=f"Conflito de código gerado: {novo}")

    return novo


@router.get("/clientes", response_model=List[PessoaOut])
def listar_clientes(db: Session = Depends(get_db)):
    return db.query(Pessoa).filter(Pessoa.tipo.ilike("CLIENTE")).order_by(Pessoa.nome).all()


@router.get("/fornecedores", response_model=List[PessoaOut])
def listar_fornecedores(db: Session = Depends(get_db)):
    return db.query(Pessoa).filter(Pessoa.tipo.ilike("FORNECEDOR")).order_by(Pessoa.nome).all()


@router.get("", response_model=List[PessoaOut])
def listar_pessoas(
    tipo: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Pessoa)
    if tipo:
        q = q.filter(Pessoa.tipo.ilike(tipo))
    return q.order_by(Pessoa.nome).all()


@router.post("", response_model=PessoaOut, status_code=201)
def criar_pessoa(payload: PessoaCreate, db: Session = Depends(get_db)):
    if not payload.tipo or not payload.nome:
        raise HTTPException(status_code=400, detail="Campos obrigatórios: tipo, nome")

    codigo = _gerar_codigo(payload.tipo, db)
    pessoa = Pessoa(**payload.model_dump(), codigo=codigo)
    db.add(pessoa)
    db.commit()
    db.refresh(pessoa)
    return pessoa


@router.put("/{id}", response_model=PessoaOut)
def atualizar_pessoa(id: int, payload: PessoaCreate, db: Session = Depends(get_db)):
    pessoa = db.query(Pessoa).filter(Pessoa.id == id).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    for k, v in payload.model_dump(exclude_unset=True).items():
        if k != "codigo":
            setattr(pessoa, k, v)

    db.commit()
    db.refresh(pessoa)
    return pessoa


@router.delete("/{id}")
def deletar_pessoa(id: int, db: Session = Depends(get_db)):
    pessoa = db.query(Pessoa).filter(Pessoa.id == id).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    db.delete(pessoa)
    db.commit()
    return {"mensagem": "Pessoa removida com sucesso"}
