import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Animal, Inseminacao
from routers.relatorios import _previsao_animal

router = APIRouter()


def _fmt(valor: Optional[str]) -> str:
    if not valor:
        return ""
    try:
        return date.fromisoformat(valor).strftime("%d/%m/%Y")
    except ValueError:
        return valor


def _calc_idade_anos(data_nascimento: Optional[str]) -> str:
    if not data_nascimento:
        return ""
    try:
        nasc = date.fromisoformat(data_nascimento)
        hoje = date.today()
        anos = hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
        return str(anos)
    except ValueError:
        return ""


def _csv_response(rows: list[list], cabecalho: list[str], nome_arquivo: str) -> StreamingResponse:
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(cabecalho)
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


@router.get("/animais")
def exportar_animais(
    brinco: Optional[str] = Query(None),
    pasto: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sexo: Optional[str] = Query(None),
    raca: Optional[str] = Query(None),
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

    animais = q.order_by(Animal.brinco).all()

    cabecalho = [
        "Brinco", "Nome", "Sexo", "Origem", "Data Compra", "Data Nascimento",
        "Raça", "Tipo", "Idade (anos)", "Status", "Pasto", "Lote", "Peso", "Última Cria",
    ]
    rows = [
        [
            a.brinco, a.nome or "", a.sexo or "", a.origem or "",
            _fmt(a.data_compra), _fmt(a.data_nascimento),
            a.raca or "", a.tipo or "", _calc_idade_anos(a.data_nascimento),
            a.status or "", a.pasto or "", a.lote or "",
            a.peso_atual if a.peso_atual is not None else "",
            _fmt(a.ult_cria),
        ]
        for a in animais
    ]

    nome = f"animais_{date.today().isoformat()}.csv"
    return _csv_response(rows, cabecalho, nome)


@router.get("/inseminacoes")
def exportar_inseminacoes(db: Session = Depends(get_db)):
    registros = db.query(Inseminacao).order_by(Inseminacao.data_insem.desc()).all()

    cabecalho = [
        "Brinco", "Data Inseminação", "Prenhez", "Qtd Crias",
        "Nasc. Crias", "Status", "Observação",
    ]
    rows = [
        [
            r.brinco, _fmt(r.data_insem), r.prenhez or "",
            r.qtd_crias if r.qtd_crias is not None else 0,
            _fmt(r.data_nasc_cria), r.status or "", r.obs or "",
        ]
        for r in registros
    ]

    nome = f"inseminacoes_{date.today().isoformat()}.csv"
    return _csv_response(rows, cabecalho, nome)


@router.get("/previsao-saida")
def exportar_previsao_saida(
    peso_alvo: float = Query(...),
    dias_gmd: int = Query(90),
    status: str = Query("ATIVO"),
    tipo: Optional[str] = Query(None),
    pasto: Optional[str] = Query(None),
    lote: Optional[str] = Query(None),
    preco_arroba: Optional[float] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Animal).filter(Animal.status.ilike(status))
    if tipo:
        q = q.filter(Animal.tipo.ilike(tipo))
    if pasto:
        q = q.filter(Animal.pasto.ilike(pasto))
    if lote:
        q = q.filter(Animal.lote.ilike(f"%{lote}%"))

    animais = q.all()
    resultado = [_previsao_animal(a, peso_alvo, dias_gmd, preco_arroba, db) for a in animais]

    cabecalho = [
        "Brinco", "Nome", "Tipo", "Raça", "Pasto", "Lote",
        "Peso Atual (kg)", "Peso Alvo (kg)", "Falta (kg)", "GMD Real (kg/dia)",
        "Qtd Pesagens", "Data Prevista", "Data Otimista", "Data Pessimista",
        "Arrobas Previstas", "Receita Estimada (R$)", "Lucro Estimado (R$)", "Situação",
    ]

    def _dd(iso):
        if not iso:
            return ""
        try:
            return date.fromisoformat(iso).strftime("%d/%m/%Y")
        except Exception:
            return iso

    rows = [
        [
            r["brinco"], r["nome"] or "", r["tipo"] or "", r["raca"] or "",
            r["pasto"] or "", r["lote"] or "",
            r["peso_atual"], r["peso_alvo"], r["diferenca_kg"],
            r["gmd_real"] if r["gmd_real"] is not None else "",
            r["qtd_pesagens"], _dd(r["data_prevista"]), _dd(r["data_otimista"]), _dd(r["data_pessimista"]),
            r["arrobas_previstas"],
            r["receita_estimada"] if r["receita_estimada"] is not None else "",
            r["lucro_estimado"] if r["lucro_estimado"] is not None else "",
            r["situacao"],
        ]
        for r in resultado
    ]

    nome = f"previsao_saida_{date.today().isoformat()}_pesoalvo_{int(peso_alvo)}kg.csv"
    return _csv_response(rows, cabecalho, nome)
