import io
import json
from datetime import date, datetime
from typing import List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from database import get_db
from models import Animal, ImportacaoBalanca, Pesagem

router = APIRouter()

# ── Mapeamento tolerante de colunas ──────────────────────────────────
_BRINCO_COLS  = {"animal id", "animal_id", "tag id", "tag_id", "brinco", "id", "animais"}
_PESO_COLS    = {"weight", "peso", "kg", "weight kg", "weight(kg)", "peso kg"}
_DATA_COLS    = {"date", "data", "fecha", "dt", "data pesagem", "data_pesagem"}
_DATE_FMTS    = ["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y",
                 "%d/%m/%y", "%m/%d/%y", "%Y/%m/%d"]


def _detect_col(columns: list[str], candidates: set) -> str | None:
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
    # tenta datetime do pandas
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


def _calcular_ganho(brinco: str, peso_novo: float, data_nova: str, db: Session):
    anterior = (
        db.query(Pesagem)
        .filter(Pesagem.brinco.ilike(brinco), Pesagem.data_pesagem < data_nova)
        .order_by(Pesagem.data_pesagem.desc())
        .first()
    )
    ganho_kg = ganho_pct = media_dia_kg = 0.0
    if anterior:
        ganho_kg = round(peso_novo - anterior.peso, 2)
        if anterior.peso:
            ganho_pct = round((ganho_kg / anterior.peso) * 100, 1)
        try:
            d1 = date.fromisoformat(anterior.data_pesagem)
            d2 = date.fromisoformat(data_nova)
            dias = (d2 - d1).days
            if dias > 0:
                media_dia_kg = round(ganho_kg / dias, 1)
        except Exception:
            pass
    return ganho_kg, ganho_pct, media_dia_kg


# ── POST /balanca/importar ────────────────────────────────────────────
@router.post("/importar")
async def importar_balanca(arquivo: UploadFile = File(...), db: Session = Depends(get_db)):
    nome = arquivo.filename or "arquivo"
    ext  = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""

    if ext not in ("csv", "xls", "xlsx"):
        raise HTTPException(status_code=400,
            detail="Formato não suportado. Use CSV, XLS ou XLSX.")

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
        raise HTTPException(status_code=400,
            detail="Colunas obrigatórias não encontradas. O arquivo deve ter colunas de Animal ID e Weight.")

    hoje = date.today().isoformat()
    lista_ignorados: List[dict] = []
    lista_erros:     List[dict] = []
    importados = 0

    for idx, row in df.iterrows():
        num_linha = int(idx) + 2  # +2: cabeçalho + índice base 0

        # brinco
        brinco_raw = str(row.get(col_brinco, "")).strip()
        if not brinco_raw or brinco_raw.lower() == "nan":
            lista_erros.append({"linha": num_linha, "motivo": "Brinco vazio"})
            continue

        # peso
        peso = _parse_peso(row.get(col_peso))
        if peso is None:
            lista_erros.append({
                "linha": num_linha,
                "motivo": f"Peso inválido: '{row.get(col_peso)}'"
            })
            continue

        # data
        data_str = None
        if col_data:
            data_str = _parse_date(row.get(col_data))
        if not data_str:
            data_str = hoje

        # verificar animal
        animal = db.query(Animal).filter(Animal.brinco.ilike(brinco_raw)).first()
        if not animal:
            lista_ignorados.append({
                "brinco": brinco_raw,
                "motivo": "Brinco não encontrado no sistema"
            })
            continue

        # verificar duplicata
        existe = db.query(Pesagem).filter(
            Pesagem.brinco.ilike(brinco_raw),
            Pesagem.data_pesagem == data_str
        ).first()
        if existe:
            lista_ignorados.append({
                "brinco": brinco_raw,
                "data": data_str,
                "motivo": "Pesagem já importada para esta data"
            })
            continue

        # calcular ganho
        ganho_kg, ganho_pct, media_dia_kg = _calcular_ganho(brinco_raw, peso, data_str, db)

        dt = date.fromisoformat(data_str)
        pesagem = Pesagem(
            brinco=animal.brinco,
            data_pesagem=data_str,
            peso=peso,
            ganho_kg=ganho_kg,
            ganho_pct=ganho_pct,
            media_dia_kg=media_dia_kg,
            mes=dt.month,
            ano=dt.year,
            pasto=animal.pasto,
        )
        db.add(pesagem)
        animal.peso_atual = peso
        db.add(animal)
        importados += 1

    db.flush()

    total     = len(df)
    n_ign     = len(lista_ignorados)
    n_err     = len(lista_erros)
    detalhes  = {"ignorados": lista_ignorados, "erros": lista_erros}

    log = ImportacaoBalanca(
        nome_arquivo    = nome,
        data_importacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_linhas    = total,
        importados      = importados,
        ignorados       = n_ign,
        erros           = n_err,
        detalhes        = json.dumps(detalhes, ensure_ascii=False),
    )
    db.add(log)
    db.commit()

    partes = [f"{importados} pesagens importadas com sucesso."]
    if n_ign: partes.append(f"{n_ign} ignoradas.")
    if n_err: partes.append(f"{n_err} com erro.")

    return {
        "sucesso":    importados > 0 or (n_err == 0 and n_ign == 0),
        "importados": importados,
        "ignorados":  n_ign,
        "erros":      n_err,
        "total":      total,
        "mensagem":   " ".join(partes),
        "detalhes":   detalhes,
    }


# ── GET /balanca/historico ────────────────────────────────────────────
@router.get("/historico")
def historico(db: Session = Depends(get_db)):
    registros = (
        db.query(ImportacaoBalanca)
        .order_by(ImportacaoBalanca.data_importacao.desc())
        .all()
    )
    return [
        {
            "id":              r.id,
            "nome_arquivo":    r.nome_arquivo,
            "data_importacao": r.data_importacao,
            "total_linhas":    r.total_linhas,
            "importados":      r.importados,
            "ignorados":       r.ignorados,
            "erros":           r.erros,
        }
        for r in registros
    ]


# ── GET /balanca/historico/{id}/detalhes ─────────────────────────────
@router.get("/historico/{id}/detalhes")
def historico_detalhes(id: int, db: Session = Depends(get_db)):
    registro = db.query(ImportacaoBalanca).filter(ImportacaoBalanca.id == id).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Importação não encontrada")
    try:
        return json.loads(registro.detalhes or "{}")
    except Exception:
        return {}
