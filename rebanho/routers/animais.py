from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date

from database import get_db
from models import Animal, Pesagem, Sanidade
from schemas import AnimalCreate, AnimalUpdate, AnimalOut, PesagemOut, SanidadeOut

router = APIRouter()


def _calc_idade(data_nascimento: str):
    try:
        nasc = date.fromisoformat(data_nascimento)
        hoje = date.today()
        anos = hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
        meses_total = (hoje.year - nasc.year) * 12 + (hoje.month - nasc.month)
        if hoje.day < nasc.day:
            meses_total -= 1
        return anos, meses_total % 12
    except Exception:
        return 0, 0


def _to_out(animal: Animal) -> dict:
    d = {c.name: getattr(animal, c.name) for c in animal.__table__.columns}
    anos, meses = _calc_idade(animal.data_nascimento or "")
    d["idade_anos"] = anos
    d["idade_meses"] = meses
    return d


def _calcular_custos(animal: "Animal"):
    if animal.valor_compra and animal.valor_compra > 0 and animal.peso_atual and animal.peso_atual > 0:
        animal.custo_kg = round(animal.valor_compra / animal.peso_atual, 2)
        animal.custo_arroba = round(animal.valor_compra / (animal.peso_atual / 15), 2)
    else:
        animal.custo_kg = None
        animal.custo_arroba = None


def _validate_and_fill(data: dict, db: Session, brinco_original: str = None):
    required = ["brinco", "sexo", "tipo", "raca", "origem", "data_nascimento", "status"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")

    if data.get("status") == "MORTO":
        if not data.get("data_morte"):
            raise HTTPException(status_code=400, detail="data_morte é obrigatória quando status = MORTO")
        if not data.get("motivo_morte"):
            raise HTTPException(status_code=400, detail="motivo_morte é obrigatório quando status = MORTO")

    if data.get("data_morte"):
        try:
            dt = date.fromisoformat(data["data_morte"])
            data["mes_morte"] = dt.month
            data["ano_morte"] = dt.year
        except ValueError:
            raise HTTPException(status_code=400, detail="data_morte inválida, use YYYY-MM-DD")

    return data


def _atualizar_pais(data: dict, db: Session):
    data_nasc = data.get("data_nascimento")
    if not data_nasc:
        return

    for campo in ("nome_pai", "nome_mae"):
        brinco_parente = data.get(campo)
        if brinco_parente:
            parente = db.query(Animal).filter(
                Animal.brinco.ilike(brinco_parente)
            ).first()
            if parente:
                parente.ult_cria = data_nasc
                db.add(parente)


@router.get("", response_model=List[AnimalOut])
def listar_animais(
    brinco: Optional[str] = Query(None),
    pasto: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sexo: Optional[str] = Query(None),
    raca: Optional[str] = Query(None),
    lote: Optional[str] = Query(None),
    sem_lote: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Animal)
    if brinco:
        q = q.filter(Animal.brinco.ilike(brinco))
    if pasto:
        q = q.filter(Animal.pasto.ilike(pasto))
    if tipo:
        q = q.filter(Animal.tipo.ilike(tipo))
    if status:
        q = q.filter(Animal.status.ilike(status))
    if sexo:
        q = q.filter(Animal.sexo.ilike(sexo))
    if raca:
        q = q.filter(Animal.raca.ilike(raca))
    if lote:
        q = q.filter(Animal.lote.ilike(f"%{lote}%"))
    if sem_lote == "1":
        q = q.filter((Animal.lote == None) | (Animal.lote == ""))

    animais = q.limit(500).all()
    return [_to_out(a) for a in animais]


@router.get("/{brinco}", response_model=AnimalOut)
def buscar_animal(brinco: str, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.brinco.ilike(brinco)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    return _to_out(animal)


@router.post("", response_model=AnimalOut, status_code=201)
def criar_animal(payload: AnimalCreate, db: Session = Depends(get_db)):
    existente = db.query(Animal).filter(Animal.brinco.ilike(payload.brinco)).first()
    if existente:
        raise HTTPException(status_code=400, detail="Brinco já cadastrado")

    data = payload.model_dump()
    _validate_and_fill(data, db)

    animal = Animal(**{k: v for k, v in data.items() if hasattr(Animal, k) and k not in ("custo_kg", "custo_arroba")})
    _calcular_custos(animal)
    db.add(animal)

    _atualizar_pais(data, db)
    db.commit()
    db.refresh(animal)
    return _to_out(animal)


@router.put("/{brinco}", response_model=AnimalOut)
def atualizar_animal(brinco: str, payload: AnimalUpdate, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.brinco.ilike(brinco)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")

    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if k != "brinco"}

    merged = {c.name: getattr(animal, c.name) for c in animal.__table__.columns}
    merged.update(update_data)

    _validate_and_fill(merged, db, brinco_original=brinco)

    for k, v in update_data.items():
        if k not in ("custo_kg", "custo_arroba"):
            setattr(animal, k, v)

    if merged.get("data_morte"):
        animal.mes_morte = merged.get("mes_morte")
        animal.ano_morte = merged.get("ano_morte")

    _calcular_custos(animal)
    _atualizar_pais(update_data, db)
    db.commit()
    db.refresh(animal)
    return _to_out(animal)


@router.delete("/{brinco}")
def deletar_animal(brinco: str, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.brinco.ilike(brinco)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    db.delete(animal)
    db.commit()
    return {"mensagem": "Animal removido com sucesso"}


@router.get("/{brinco}/pesagens", response_model=List[PesagemOut])
def pesagens_do_animal(brinco: str, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.brinco.ilike(brinco)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    return (
        db.query(Pesagem)
        .filter(Pesagem.brinco.ilike(brinco))
        .order_by(Pesagem.data_pesagem.desc())
        .all()
    )


@router.get("/{brinco}/sanidade", response_model=List[SanidadeOut])
def sanidade_do_animal(brinco: str, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.brinco.ilike(brinco)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    return (
        db.query(Sanidade)
        .filter(Sanidade.brinco.ilike(brinco))
        .order_by(Sanidade.data.desc())
        .all()
    )
