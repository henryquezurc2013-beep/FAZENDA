import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from database import supabase
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


def _csv_response(rows: list, cabecalho: list, nome_arquivo: str) -> StreamingResponse:
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
):
    q = supabase.table("animais").select("*")
    if brinco:
        q = q.ilike("brinco", brinco)
    if pasto:
        q = q.ilike("pasto", pasto)
    if tipo:
        q = q.ilike("tipo", tipo)
    if status:
        q = q.ilike("status", status)
    if sexo:
        q = q.ilike("sexo", sexo)
    if raca:
        q = q.ilike("raca", raca)
    animais = q.order("brinco").execute().data
    cabecalho = [
        "Brinco", "Nome", "Sexo", "Origem", "Data Compra", "Data Nascimento",
        "Raça", "Tipo", "Idade (anos)", "Status", "Pasto", "Lote", "Peso", "Última Cria",
    ]
    rows = [
        [
            a["brinco"], a.get("nome") or "", a.get("sexo") or "", a.get("origem") or "",
            _fmt(a.get("data_compra")), _fmt(a.get("data_nascimento")),
            a.get("raca") or "", a.get("tipo") or "", _calc_idade_anos(a.get("data_nascimento")),
            a.get("status") or "", a.get("pasto") or "", a.get("lote") or "",
            a.get("peso_atual") if a.get("peso_atual") is not None else "",
            _fmt(a.get("ult_cria")),
        ]
        for a in animais
    ]
    return _csv_response(rows, cabecalho, f"animais_{date.today().isoformat()}.csv")


@router.get("/inseminacoes")
def exportar_inseminacoes():
    registros = supabase.table("inseminacoes").select("*").order("data_insem", desc=True).execute().data
    cabecalho = [
        "Brinco", "Data Inseminação", "Prenhez", "Qtd Crias",
        "Nasc. Crias", "Status", "Observação",
    ]
    rows = [
        [
            r["brinco"], _fmt(r.get("data_insem")), r.get("prenhez") or "",
            r.get("qtd_crias") if r.get("qtd_crias") is not None else 0,
            _fmt(r.get("data_nasc_cria")), r.get("status") or "", r.get("obs") or "",
        ]
        for r in registros
    ]
    return _csv_response(rows, cabecalho, f"inseminacoes_{date.today().isoformat()}.csv")


@router.get("/previsao-saida")
def exportar_previsao_saida(
    peso_alvo: float = Query(...),
    dias_gmd: int = Query(90),
    status: str = Query("ATIVO"),
    tipo: Optional[str] = Query(None),
    pasto: Optional[str] = Query(None),
    lote: Optional[str] = Query(None),
    preco_arroba: Optional[float] = Query(None),
):
    q = supabase.table("animais").select("*").ilike("status", status)
    if tipo:
        q = q.ilike("tipo", tipo)
    if pasto:
        q = q.ilike("pasto", pasto)
    if lote:
        q = q.ilike("lote", f"%{lote}%")
    animais = q.execute().data
    resultado = [_previsao_animal(a, peso_alvo, dias_gmd, preco_arroba, None) for a in animais]

    def _dd(iso):
        if not iso:
            return ""
        try:
            return date.fromisoformat(iso).strftime("%d/%m/%Y")
        except Exception:
            return iso

    cabecalho = [
        "Brinco", "Nome", "Tipo", "Raça", "Pasto", "Lote",
        "Peso Atual (kg)", "Peso Alvo (kg)", "Falta (kg)", "GMD Real (kg/dia)",
        "Qtd Pesagens", "Data Prevista", "Data Otimista", "Data Pessimista",
        "Arrobas Previstas", "Receita Estimada (R$)", "Lucro Estimado (R$)", "Situação",
    ]
    rows = [
        [
            r["brinco"], r.get("nome") or "", r.get("tipo") or "", r.get("raca") or "",
            r.get("pasto") or "", r.get("lote") or "",
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
