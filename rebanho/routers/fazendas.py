from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Animal, Fazenda, LancamentoRacao, LoteAnimal, Pesagem,
    Piquete, PlanoNutricional,
)

router = APIRouter()


class FazendaIn(BaseModel):
    nome: str
    apelido: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    area_ha: Optional[float] = None
    cor: Optional[str] = '#1B5E20'


def _kpis(f: Fazenda, db: Session) -> dict:
    total_animais = db.query(Animal).filter(Animal.fazenda_id == f.id).count()
    total_ativos  = db.query(Animal).filter(
        Animal.fazenda_id == f.id, Animal.status == "ATIVO"
    ).count()
    total_piquetes = db.query(Piquete).filter(Piquete.fazenda_id == f.id).count()

    # UA/ha média dos lotes vinculados aos piquetes desta fazenda
    piq_ids = [p.id for p in db.query(Piquete).filter(Piquete.fazenda_id == f.id).all()]
    ua_ha_media = None
    if piq_ids:
        from models import LotePasto
        lotes_pasto = db.query(LotePasto).filter(
            LotePasto.piquete_id.in_(piq_ids),
            LotePasto.status == "ATIVO",
        ).all()
        if lotes_pasto:
            # estimate UA/ha from total animals and farm area
            pass

    return {
        "id": f.id, "nome": f.nome, "apelido": f.apelido,
        "cidade": f.cidade, "uf": f.uf, "area_ha": f.area_ha,
        "cor": f.cor, "ativo": f.ativo,
        "total_animais": total_animais, "total_ativos": total_ativos,
        "total_piquetes": total_piquetes, "ua_ha_media": ua_ha_media,
    }


@router.get("")
def listar_fazendas(db: Session = Depends(get_db)):
    fazendas = db.query(Fazenda).filter(Fazenda.ativo == True).order_by(Fazenda.id).all()
    return [_kpis(f, db) for f in fazendas]


@router.post("")
def criar_fazenda(body: FazendaIn, db: Session = Depends(get_db)):
    if db.query(Fazenda).filter(Fazenda.nome == body.nome).first():
        raise HTTPException(400, "Já existe uma fazenda com esse nome")
    f = Fazenda(**body.model_dump())
    db.add(f); db.commit(); db.refresh(f)
    return {"id": f.id, "ok": True}


@router.put("/{fid}")
def editar_fazenda(fid: int, body: FazendaIn, db: Session = Depends(get_db)):
    f = db.query(Fazenda).filter(Fazenda.id == fid).first()
    if not f:
        raise HTTPException(404, "Fazenda não encontrada")
    for k, v in body.model_dump().items():
        setattr(f, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/{fid}")
def excluir_fazenda(fid: int, db: Session = Depends(get_db)):
    f = db.query(Fazenda).filter(Fazenda.id == fid).first()
    if not f:
        raise HTTPException(404, "Fazenda não encontrada")
    tem_animais  = db.query(Animal).filter(Animal.fazenda_id == fid).first()
    tem_piquetes = db.query(Piquete).filter(Piquete.fazenda_id == fid).first()
    if tem_animais or tem_piquetes:
        raise HTTPException(400, "Fazenda possui animais ou piquetes vinculados. Remova-os primeiro.")
    db.delete(f); db.commit()
    return {"ok": True}


@router.get("/{fid}/resumo")
def resumo_fazenda(fid: int, db: Session = Depends(get_db)):
    f = db.query(Fazenda).filter(Fazenda.id == fid).first()
    if not f:
        raise HTTPException(404, "Fazenda não encontrada")

    hoje = date.today()
    mes_str = hoje.strftime("%Y-%m")

    total_ativos = db.query(Animal).filter(
        Animal.fazenda_id == fid, Animal.status == "ATIVO"
    ).count()

    from models import Compra, Despesa, Venda
    receita = db.query(func.sum(Venda.valor_total)).filter(
        Venda.data.like(f"{mes_str}%")
    ).scalar() or 0
    despesa = db.query(func.sum(Despesa.valor)).filter(
        Despesa.vencimento.like(f"{mes_str}%"),
        Despesa.status == "PENDENTE",
    ).scalar() or 0

    ultima_pes = db.query(Pesagem).filter(
        Pesagem.fazenda_id == fid
    ).order_by(Pesagem.data_pesagem.desc()).first()

    piquetes = db.query(Piquete).filter(Piquete.fazenda_id == fid).all()
    from routers.pastagem import semaforo_piquete
    verde = sum(1 for p in piquetes if semaforo_piquete(p.id, db)["semaforo"] == "VERDE")
    ocupado = sum(1 for p in piquetes if semaforo_piquete(p.id, db)["semaforo"] == "OCUPADO")

    return {
        "fazenda": {"id": f.id, "nome": f.nome, "cor": f.cor, "apelido": f.apelido,
                    "cidade": f.cidade, "uf": f.uf, "area_ha": f.area_ha},
        "rebanho": {"total_ativo": total_ativos},
        "pastagem": {"verde": verde, "ocupado": ocupado},
        "financeiro": {"receita_mes": round(float(receita), 2),
                       "despesa_mes": round(float(despesa), 2),
                       "saldo_mes":   round(float(receita) - float(despesa), 2)},
        "ultima_pesagem": ultima_pes.data_pesagem if ultima_pes else None,
    }


def seed_fazendas(db: Session):
    if db.query(Fazenda).first():
        return
    db.add(Fazenda(
        nome="Fazenda Ipanema", apelido="IPM",
        cidade="Luziânia", uf="GO", area_ha=500, cor="#0d1f3c",
    ))
    db.add(Fazenda(
        nome="Fazenda São João", apelido="SJO",
        cidade="Cristalina", uf="GO", area_ha=300, cor="#14532d",
    ))
    db.commit()
