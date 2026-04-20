import csv
import io
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Animal, Inseminacao
from schemas import InseminacaoCreate, InseminacaoOut

router = APIRouter()


def _fmt_data(valor: Optional[str]) -> str:
    if not valor:
        return ""
    try:
        return date.fromisoformat(valor).strftime("%d/%m/%Y")
    except ValueError:
        return valor


@router.get("/exportar")
def exportar_inseminacoes(
    brinco: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Inseminacao)
    if brinco:
        q = q.filter(Inseminacao.brinco.ilike(brinco))
    if status:
        q = q.filter(Inseminacao.status.ilike(status))
    if data_inicio:
        q = q.filter(Inseminacao.data_insem >= data_inicio)
    if data_fim:
        q = q.filter(Inseminacao.data_insem <= data_fim)
    registros = q.order_by(Inseminacao.data_insem.desc()).all()

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["Brinco", "Data Inseminação", "Prenhez", "Qtd Crias",
                     "Nascimento Crias", "Status", "Observação"])
    for r in registros:
        writer.writerow([
            r.brinco,
            _fmt_data(r.data_insem),
            r.prenhez or "",
            r.qtd_crias if r.qtd_crias is not None else 0,
            _fmt_data(r.data_nasc_cria),
            r.status or "",
            r.obs or "",
        ])

    output.seek(0)
    nome_arquivo = f"inseminacoes_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


@router.get("", response_model=List[InseminacaoOut])
def listar_inseminacoes(
    brinco: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Inseminacao)
    if brinco:
        q = q.filter(Inseminacao.brinco.ilike(brinco))
    if status:
        q = q.filter(Inseminacao.status.ilike(status))
    if data_inicio:
        q = q.filter(Inseminacao.data_insem >= data_inicio)
    if data_fim:
        q = q.filter(Inseminacao.data_insem <= data_fim)
    return q.order_by(Inseminacao.data_insem.desc()).all()


@router.post("", response_model=InseminacaoOut, status_code=201)
def criar_inseminacao(payload: InseminacaoCreate, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.brinco.ilike(payload.brinco)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    if animal.sexo and animal.sexo.upper() == "MACHO":
        raise HTTPException(status_code=400, detail="Inseminação só pode ser registrada para fêmeas")

    missing = [f for f in ("data_insem", "status") if not getattr(payload, f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")

    data = payload.model_dump()
    if not data.get("status"):
        data["status"] = "AGUARDANDO"

    registro = Inseminacao(**data)
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


@router.put("/{id}", response_model=InseminacaoOut)
def atualizar_inseminacao(id: int, payload: InseminacaoCreate, db: Session = Depends(get_db)):
    registro = db.query(Inseminacao).filter(Inseminacao.id == id).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Inseminação não encontrada")

    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if k != "brinco"}
    for k, v in update_data.items():
        setattr(registro, k, v)

    db.commit()
    db.refresh(registro)
    return registro


@router.delete("/{id}")
def deletar_inseminacao(id: int, db: Session = Depends(get_db)):
    registro = db.query(Inseminacao).filter(Inseminacao.id == id).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Inseminação não encontrada")
    db.delete(registro)
    db.commit()
    return {"mensagem": "Inseminação removida com sucesso"}
