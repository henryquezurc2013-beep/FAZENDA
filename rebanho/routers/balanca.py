import io
import json
from datetime import date, datetime, timedelta
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from database import supabase
from constants import DATA_NASCIMENTO_OFFSET_DIAS

router = APIRouter()

_BRINCO_COLS  = {"animal id", "animal_id", "tag id", "tag_id",
                 "brinco", "id", "idv", "eid", "vid", "ear tag",
                 "tag", "animais"}
_PESO_COLS    = {"weight", "peso", "kg", "weight kg", "weight(kg)", "peso kg"}
_DATA_COLS    = {"date", "data", "fecha", "dt", "data pesagem", "data_pesagem"}
_DATE_FMTS    = ["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y",
                 "%d/%m/%y", "%m/%d/%y", "%Y/%m/%d"]


def _detect_col(columns: list, candidates: set):
    for col in columns:
        if col.strip().lower() in candidates:
            return col
    return None


def _parse_date(valor) -> str | None:
    if pd.isna(valor):
        return None
    s = str(valor).strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return pd.to_datetime(valor).strftime("%Y-%m-%d")
    except Exception:
        return None


def _parse_peso(valor) -> float | None:
    if pd.isna(valor):
        return None
    s = str(valor).strip().upper().replace("KG", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _ler_arquivo(conteudo: bytes, nome: str) -> pd.DataFrame:
    ext = nome.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        for sep in [",", ";"]:
            try:
                df = pd.read_csv(io.BytesIO(conteudo), sep=sep, dtype=str)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue
        return pd.read_csv(io.BytesIO(conteudo), dtype=str)
    elif ext == "xlsx":
        return pd.read_excel(io.BytesIO(conteudo), engine="openpyxl", dtype=str)
    elif ext == "xls":
        return pd.read_excel(io.BytesIO(conteudo), engine="xlrd", dtype=str)
    raise ValueError(f"Extensão não suportada: {ext}")


def _calcular_ganho(brinco: str, peso_novo: float, data_nova: str):
    rows = supabase.table("pesagens").select("peso_kg,data").ilike("brinco", brinco).lt("data", data_nova).order("data", desc=True).limit(1).execute().data
    anterior = rows[0] if rows else None
    ganho_kg = 0.0
    gmd = 0.0
    dias_periodo = 0
    if anterior:
        ganho_kg = round(peso_novo - anterior["peso_kg"], 2)
        try:
            dias_periodo = (date.fromisoformat(data_nova) - date.fromisoformat(anterior["data"])).days
            if dias_periodo > 0:
                gmd = round(ganho_kg / dias_periodo, 3)
        except Exception:
            pass
    return ganho_kg, gmd, dias_periodo


@router.post("/importar")
async def importar_balanca(
    arquivo: UploadFile = File(...),
    cadastrar_novos: bool = Form(True),
    sexo_padrao: str = Form("MACHO"),
    raca_padrao: str = Form("NELORE"),
    tipo_padrao: str = Form("GARROTE"),
    origem_padrao: str = Form("COMPRA"),
    fornecedor: str = Form("Importação Balança"),
    valor_medio: str = Form(""),
    gerar_compra_agregada: bool = Form(True),
):
    nome = arquivo.filename or "arquivo"
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in ("csv", "xls", "xlsx"):
        raise HTTPException(status_code=400, detail="Formato não suportado. Use CSV, XLS ou XLSX.")
    conteudo = await arquivo.read()
    try:
        df = _ler_arquivo(conteudo, nome)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {e}")

    colunas = list(df.columns)
    col_brinco = _detect_col(colunas, _BRINCO_COLS)
    col_peso   = _detect_col(colunas, _PESO_COLS)
    col_data   = _detect_col(colunas, _DATA_COLS)
    if not col_brinco or not col_peso:
        raise HTTPException(status_code=400, detail="Colunas obrigatórias não encontradas.")

    # valor_medio chega como string (form HTML); parseia tolerante (vírgula/ponto).
    # Vazio, zero ou negativo → ignora (animais ficam sem valor_compra e nenhum
    # lançamento agregado é criado).
    valor_medio_float: Optional[float] = None
    if valor_medio:
        try:
            v = float(str(valor_medio).replace(",", "."))
            if v > 0:
                valor_medio_float = v
        except ValueError:
            pass

    hoje = date.today().isoformat()
    lista_ignorados:   List[dict] = []
    lista_erros:       List[dict] = []
    lista_cadastrados: List[dict] = []
    importados = 0
    novos_cadastrados = 0
    data_primeira_pesagem: Optional[str] = None  # data do lote → vira data de /compras

    for idx, row in df.iterrows():
        num_linha = int(idx) + 2
        brinco_raw = str(row.get(col_brinco, "")).strip()
        if not brinco_raw or brinco_raw.lower() == "nan":
            lista_erros.append({"linha": num_linha, "motivo": "Brinco vazio"})
            continue
        peso = _parse_peso(row.get(col_peso))
        if peso is None:
            lista_erros.append({"linha": num_linha, "motivo": f"Peso inválido: '{row.get(col_peso)}'"})
            continue
        data_str = None
        if col_data:
            data_str = _parse_date(row.get(col_data))
        if not data_str:
            data_str = hoje
        if data_primeira_pesagem is None:
            data_primeira_pesagem = data_str

        animal_rows = supabase.table("animais").select("brinco,pasto_atual,fazenda_id").ilike("brinco", brinco_raw).limit(1).execute().data

        # Brinco novo? Comportamento depende de cadastrar_novos.
        if not animal_rows:
            if not cadastrar_novos:
                lista_ignorados.append({"brinco": brinco_raw, "motivo": "Brinco não encontrado no sistema"})
                continue
            # Auto-cadastra animal novo com defaults da UI.
            try:
                dt_compra = date.fromisoformat(data_str)
                data_nascimento = (dt_compra - timedelta(days=DATA_NASCIMENTO_OFFSET_DIAS)).isoformat()
                novo_animal = {
                    "brinco":          brinco_raw,
                    "sexo":            sexo_padrao,
                    "raca":            raca_padrao,
                    "tipo":            tipo_padrao,
                    "origem":          origem_padrao,
                    "status":          "ATIVO",
                    "fazenda_id":      1,
                    "data_compra":     data_str,
                    "data_nascimento": data_nascimento,
                    "peso_atual":      peso,
                }
                if valor_medio_float and peso > 0:
                    novo_animal["valor_compra"] = valor_medio_float
                    novo_animal["custo_kg"]     = round(valor_medio_float / peso, 2)
                    novo_animal["custo_arroba"] = round(valor_medio_float / (peso / 15), 2)
                supabase.table("animais").insert(novo_animal).execute()
                novos_cadastrados += 1
                lista_cadastrados.append({"brinco": brinco_raw, "data": data_str, "peso": peso})
                # Substitui animal_rows pra cair no fluxo normal de pesagem abaixo.
                animal_rows = [{"brinco": brinco_raw, "pasto_atual": None, "fazenda_id": 1}]
            except Exception as e:
                lista_erros.append({
                    "linha": num_linha, "brinco": brinco_raw,
                    "motivo": f"Falha ao cadastrar animal novo: {str(e)[:120]}"
                })
                continue

        animal = animal_rows[0]
        existe = supabase.table("pesagens").select("id").ilike("brinco", brinco_raw).eq("data", data_str).limit(1).execute().data
        if existe:
            lista_ignorados.append({"brinco": brinco_raw, "data": data_str, "motivo": "Pesagem já importada para esta data"})
            continue
        fazenda_id = animal.get("fazenda_id")
        if not fazenda_id:
            lista_ignorados.append({
                "brinco": brinco_raw,
                "data": data_str,
                "motivo": "Animal sem fazenda_id cadastrada"
            })
            continue
        ganho_kg, gmd, dias_periodo = _calcular_ganho(brinco_raw, peso, data_str)
        supabase.table("pesagens").insert({
            "brinco": animal["brinco"],
            "data": data_str,
            "peso_kg": peso,
            "ganho_kg": ganho_kg,
            "gmd": gmd,
            "dias_periodo": dias_periodo,
            "pasto": animal.get("pasto_atual"),
            "fazenda_id": fazenda_id,
        }).execute()
        supabase.table("animais").update({"peso_atual": peso}).ilike("brinco", brinco_raw).execute()
        importados += 1

    # Lançamento agregado em /compras: só cria se houve cadastro de animais novos
    # E o valor_medio foi informado (não inventa valor de compra).
    compra_id = None
    if gerar_compra_agregada and novos_cadastrados > 0 and valor_medio_float and data_primeira_pesagem:
        try:
            dt_compra = date.fromisoformat(data_primeira_pesagem)
            valor_total = round(novos_cadastrados * valor_medio_float, 2)
            row_compra = supabase.table("compras").insert({
                "fornecedor":  fornecedor,
                "data":        data_primeira_pesagem,
                "descricao":   f"Importação balança — {novos_cadastrados} animais novos cadastrados",
                "valor_unit":  valor_medio_float,
                "quantidade":  novos_cadastrados,
                "valor_total": valor_total,
                "mes":         dt_compra.month,
                "ano":         dt_compra.year,
            }).execute().data[0]
            compra_id = row_compra["id"]
        except Exception as e:
            print(f"[importar_balanca] aviso: falhou ao gravar lancamento de compra: {e}")

    total = len(df)
    n_ign = len(lista_ignorados)
    n_err = len(lista_erros)
    detalhes = {
        "ignorados":   lista_ignorados,
        "erros":       lista_erros,
        "cadastrados": lista_cadastrados,
    }
    supabase.table("importacoes_balanca").insert({
        "nome_arquivo": nome,
        "data_importacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_linhas": total,
        "importados": importados,
        "ignorados": n_ign,
        "erros": n_err,
        "detalhes": json.dumps(detalhes, ensure_ascii=False),
    }).execute()

    partes = [f"{importados} pesagens importadas com sucesso."]
    if novos_cadastrados:
        partes.append(f"{novos_cadastrados} animais novos cadastrados.")
    if n_ign:
        partes.append(f"{n_ign} ignoradas.")
    if n_err:
        partes.append(f"{n_err} com erro.")
    return {
        "sucesso":           importados > 0 or (n_err == 0 and n_ign == 0),
        "importados":        importados,
        "novos_cadastrados": novos_cadastrados,
        "ignorados":         n_ign,
        "erros":             n_err,
        "total":             total,
        "compra_id":         compra_id,
        "mensagem":          " ".join(partes),
        "detalhes":          detalhes,
    }


@router.get("/historico")
def historico():
    return supabase.table("importacoes_balanca").select("id,nome_arquivo,data_importacao,total_linhas,importados,ignorados,erros").order("data_importacao", desc=True).execute().data


@router.get("/historico/{id}/detalhes")
def historico_detalhes(id: int):
    rows = supabase.table("importacoes_balanca").select("detalhes").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Importação não encontrada")
    try:
        return json.loads(rows[0].get("detalhes") or "{}")
    except Exception:
        return {}
