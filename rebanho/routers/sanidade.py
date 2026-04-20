from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from database import get_db
from models import Animal, Sanidade
from schemas import SanidadeCreate, SanidadeOut, SanidadeGrupo

router = APIRouter()


@router.get("", response_model=List[SanidadeOut])
def listar_sanidade(
    brinco: Optional[str] = Query(None),
    classificacao: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Sanidade)
    if brinco:
        q = q.filter(Sanidade.brinco.ilike(brinco))
    if classificacao:
        q = q.filter(Sanidade.classificacao.ilike(classificacao))
    if data_inicio:
        q = q.filter(Sanidade.data >= data_inicio)
    if data_fim:
        q = q.filter(Sanidade.data <= data_fim)
    return q.order_by(Sanidade.data.desc()).all()


@router.post("", response_model=SanidadeOut, status_code=201)
def criar_sanidade(payload: SanidadeCreate, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.brinco.ilike(payload.brinco)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")

    missing = [f for f in ("data", "medicamento", "classificacao", "status") if not getattr(payload, f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")

    registro = Sanidade(**payload.model_dump())
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


@router.post("/grupo")
def criar_sanidade_grupo(payload: SanidadeGrupo, db: Session = Depends(get_db)):
    salvos = 0
    erros: List[str] = []

    for brinco in payload.brincos:
        animal = db.query(Animal).filter(Animal.brinco.ilike(brinco)).first()
        if not animal:
            erros.append(brinco)
            continue

        registro = Sanidade(
            brinco=animal.brinco,
            data=payload.data,
            medicamento=payload.medicamento,
            quantidade=payload.quantidade,
            unidade=payload.unidade,
            classificacao=payload.classificacao,
            status=payload.status,
            obs=payload.obs,
        )
        db.add(registro)
        salvos += 1

    db.commit()

    partes = [f"{salvos} registros lançados com sucesso."]
    if erros:
        partes.append(f"{len(erros)} brincos não encontrados: {erros}")
    else:
        partes.append("0 brincos não encontrados.")

    return {"salvos": salvos, "erros": erros, "mensagem": " ".join(partes)}


@router.put("/{id}", response_model=SanidadeOut)
def atualizar_sanidade(id: int, payload: SanidadeCreate, db: Session = Depends(get_db)):
    registro = db.query(Sanidade).filter(Sanidade.id == id).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de sanidade não encontrado")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(registro, k, v)

    db.commit()
    db.refresh(registro)
    return registro


@router.delete("/{id}")
def deletar_sanidade(id: int, db: Session = Depends(get_db)):
    registro = db.query(Sanidade).filter(Sanidade.id == id).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de sanidade não encontrado")
    db.delete(registro)
    db.commit()
    return {"mensagem": "Registro removido com sucesso"}
