import io
import json
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from database import supabase, get_fazenda_id

router = APIRouter()

# Supabase animais columns:
# id, fazenda_id, brinco, nome, tipo, raca, sexo, data_nascimento, data_compra,
# origem, valor_compra, pasto_atual, peso_atual, status, data_morte, motivo_morte,
# custo_kg, custo_arroba, obs, criado_em

_ALLOWED_FIELDS = {
    "brinco", "nome", "tipo", "raca", "sexo", "data_nascimento", "data_compra",
    "origem", "valor_compra", "pasto_atual", "peso_atual", "status", "data_morte",
    "motivo_morte", "custo_kg", "custo_arroba", "obs", "fazenda_id",
}


# ── Importação em massa (POST /animais/importar) ──────────────────────────
# Heurísticas amplas (case-insensitive, com/sem acento) para detectar colunas
# do CSV/XLS de entrada. Mapeiam para 3 campos obrigatórios: brinco, peso, valor.
_BRINCO_COLS_IMP = {"brinco", "id", "tag", "animal", "animal id", "ear tag"}
_PESO_COLS_IMP   = {"peso", "peso entrada", "peso_kg", "weight", "kg"}
_VALOR_COLS_IMP  = {"valor", "preco", "preço", "custo", "valor unit", "preco unit"}

# Defaults aplicados a todos os animais da importação (carga inicial assume
# rebanho homogêneo — gado de corte macho nelore garrote comprado).
_DEFAULTS_IMP = {
    "sexo":   "MACHO",
    "raca":   "NELORE",
    "tipo":   "GARROTE",
    "origem": "COMPRA",
    "status": "ATIVO",
}
# Estimativa de idade na compra: 8 meses → data_nascimento = data_compra - 240 dias.
_DATA_NASCIMENTO_OFFSET_DIAS = 240


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


def _to_out(animal: dict) -> dict:
    d = dict(animal)
    anos, meses = _calc_idade(animal.get("data_nascimento") or "")
    d["idade_anos"] = anos
    d["idade_meses"] = meses
    # Backward compat: expose pasto_atual as pasto
    d["pasto"] = animal.get("pasto_atual")
    return d


def _calcular_custos(data: dict) -> dict:
    vc = data.get("valor_compra")
    pa = data.get("peso_atual")
    if vc and vc > 0 and pa and pa > 0:
        data["custo_kg"] = round(vc / pa, 2)
        data["custo_arroba"] = round(vc / (pa / 15), 2)
    else:
        data["custo_kg"] = None
        data["custo_arroba"] = None
    return data


def _clean(data: dict) -> dict:
    """Keep only fields that exist in Supabase animais table."""
    # Map old field names to new
    if "pasto" in data and "pasto_atual" not in data:
        data["pasto_atual"] = data.pop("pasto")
    elif "pasto" in data:
        data.pop("pasto")
    # Remove fields not in Supabase
    return {k: v for k, v in data.items() if k in _ALLOWED_FIELDS}


def _validate_and_fill(data: dict):
    required = ["brinco", "sexo", "tipo", "raca", "origem", "data_nascimento", "status"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campos obrigatórios: {', '.join(missing)}")
    if data.get("status") == "MORTO":
        if not data.get("data_morte"):
            raise HTTPException(status_code=400, detail="data_morte é obrigatória quando status = MORTO")
        if not data.get("motivo_morte"):
            raise HTTPException(status_code=400, detail="motivo_morte é obrigatório quando status = MORTO")
    return data


@router.get("")
def listar_animais(
    request: Request,
    brinco: Optional[str] = Query(None),
    pasto: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sexo: Optional[str] = Query(None),
    raca: Optional[str] = Query(None),
    lote: Optional[str] = Query(None),
    sem_lote: Optional[str] = Query(None),
):
    fid = get_fazenda_id(request)
    q = supabase.table("animais").select("*")
    if fid > 0:
        q = q.eq("fazenda_id", fid)
    if brinco:
        q = q.ilike("brinco", brinco)
    if pasto:
        q = q.ilike("pasto_atual", pasto)
    if tipo:
        q = q.ilike("tipo", tipo)
    if status:
        q = q.ilike("status", status)
    if sexo:
        q = q.ilike("sexo", sexo)
    if raca:
        q = q.ilike("raca", raca)
    rows = q.limit(500).execute().data

    if lote or sem_lote == "1":
        # lote_animais lookup
        la_q = supabase.table("lote_animais").select("brinco,lote_id")
        if fid > 0:
            la_q = la_q.eq("fazenda_id", fid)
        la_rows = la_q.is_("data_saida", "null").execute().data
        brinco_lote = {r["brinco"]: r["lote_id"] for r in la_rows}
        if sem_lote == "1":
            rows = [r for r in rows if r.get("brinco") not in brinco_lote]
        if lote:
            lote_ids = [r["id"] for r in supabase.table("lotes").select("id,nome").ilike("nome", f"%{lote}%").execute().data]
            rows = [r for r in rows if brinco_lote.get(r.get("brinco")) in lote_ids]

    return [_to_out(a) for a in rows]


@router.get("/importacoes")
def listar_importacoes_animais():
    """Histórico de importações em massa (carga via POST /animais/importar)."""
    return supabase.table("importacoes_animais").select(
        "id,nome_arquivo,total_linhas,importados,ignorados,criado_em,fazenda_id"
    ).order("criado_em", desc=True).execute().data


@router.get("/importacoes/{id}/detalhes")
def detalhes_importacao_animais(id: int):
    """Detalhes (lista de ignorados) de uma importação específica."""
    rows = supabase.table("importacoes_animais").select("detalhes").eq("id", id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Importação não encontrada")
    return rows[0].get("detalhes") or {}


# NOTA: GETs de /importacoes precisam vir ANTES de /{brinco} senão FastAPI
# casa o path dinâmico primeiro e retorna 404 "Animal não encontrado".
@router.get("/{brinco}")
def buscar_animal(brinco: str):
    rows = supabase.table("animais").select("*").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    return _to_out(rows[0])


@router.post("", status_code=201)
def criar_animal(request: Request, body: dict):
    existing = supabase.table("animais").select("id").ilike("brinco", body.get("brinco", "")).limit(1).execute().data
    if existing:
        raise HTTPException(status_code=400, detail="Brinco já cadastrado")
    data = _clean(dict(body))
    _validate_and_fill(data)
    fid = get_fazenda_id(request)
    if fid > 0:
        data["fazenda_id"] = fid
    _calcular_custos(data)
    result = supabase.table("animais").insert(data).execute().data[0]
    return _to_out(result)


# ── Importação em massa ──────────────────────────────────────────────────

def _ler_arquivo_animais(conteudo: bytes, nome: str) -> pd.DataFrame:
    """Lê CSV/XLS/XLSX como string (espelha balanca._ler_arquivo)."""
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


def _detectar_coluna(df: pd.DataFrame, candidatos: set) -> Optional[str]:
    """Encontra a primeira coluna do DF cujo nome (lower+strip) bate com algum candidato."""
    for col in df.columns:
        if str(col).strip().lower() in candidatos:
            return col
    return None


def _parse_numero(valor) -> Optional[float]:
    """Parsa peso/valor com tolerância (R$, kg, vírgula decimal). None se inválido."""
    if pd.isna(valor):
        return None
    s = str(valor).strip().upper()
    s = s.replace("KG", "").replace("R$", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return None


@router.post("/importar")
async def importar_animais(
    request: Request,
    arquivo: UploadFile = File(...),
    gerar_compra_agregada: bool = Form(True),
    fornecedor: str = Form("Importação"),
    data_compra: Optional[str] = Form(None),
):
    nome = arquivo.filename or "arquivo"
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in ("csv", "xls", "xlsx"):
        raise HTTPException(status_code=400, detail="Formato não suportado. Use CSV, XLS ou XLSX.")
    conteudo = await arquivo.read()
    try:
        df = _ler_arquivo_animais(conteudo, nome)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {e}")

    col_brinco = _detectar_coluna(df, _BRINCO_COLS_IMP)
    col_peso   = _detectar_coluna(df, _PESO_COLS_IMP)
    col_valor  = _detectar_coluna(df, _VALOR_COLS_IMP)
    if not col_brinco or not col_peso or not col_valor:
        raise HTTPException(
            status_code=400,
            detail="Colunas obrigatórias não encontradas. A planilha precisa ter colunas para brinco, peso e valor."
        )

    # Parse data_compra (default = hoje); data_nascimento = compra - 240 dias.
    if data_compra:
        try:
            dt_compra = date.fromisoformat(data_compra)
        except ValueError:
            raise HTTPException(status_code=400, detail="data_compra inválida, use YYYY-MM-DD.")
    else:
        dt_compra = date.today()
    data_compra_iso = dt_compra.isoformat()
    data_nascimento_iso = (dt_compra - timedelta(days=_DATA_NASCIMENTO_OFFSET_DIAS)).isoformat()

    fid = get_fazenda_id(request)
    fazenda_id_final = fid if fid > 0 else 1

    lista_ignorados: List[dict] = []
    importados = 0
    soma_valores = 0.0

    for idx, row in df.iterrows():
        num_linha = int(idx) + 2
        brinco_raw = str(row.get(col_brinco, "")).strip()
        if not brinco_raw or brinco_raw.lower() == "nan":
            lista_ignorados.append({"linha": num_linha, "motivo": "Brinco vazio"})
            continue
        peso = _parse_numero(row.get(col_peso))
        if peso is None or peso <= 0:
            lista_ignorados.append({
                "linha": num_linha, "brinco": brinco_raw,
                "motivo": f"Peso inválido: '{row.get(col_peso)}'"
            })
            continue
        valor = _parse_numero(row.get(col_valor))
        if valor is None or valor <= 0:
            lista_ignorados.append({
                "linha": num_linha, "brinco": brinco_raw,
                "motivo": f"Valor inválido: '{row.get(col_valor)}'"
            })
            continue

        # Brinco já existe? (mesmo padrão do POST "" individual)
        existing = supabase.table("animais").select("id").ilike("brinco", brinco_raw).limit(1).execute().data
        if existing:
            lista_ignorados.append({
                "linha": num_linha, "brinco": brinco_raw,
                "motivo": "Brinco já cadastrado"
            })
            continue

        custo_kg = round(valor / peso, 2)
        custo_arroba = round(valor / (peso / 15), 2)

        animal_data = {
            "brinco":          brinco_raw,
            "sexo":            _DEFAULTS_IMP["sexo"],
            "raca":            _DEFAULTS_IMP["raca"],
            "tipo":            _DEFAULTS_IMP["tipo"],
            "origem":          _DEFAULTS_IMP["origem"],
            "status":          _DEFAULTS_IMP["status"],
            "fazenda_id":      fazenda_id_final,
            "peso_atual":      peso,
            "valor_compra":    valor,
            "custo_kg":        custo_kg,
            "custo_arroba":    custo_arroba,
            "data_nascimento": data_nascimento_iso,
            "data_compra":     data_compra_iso,
        }
        try:
            supabase.table("animais").insert(animal_data).execute()
            importados += 1
            soma_valores += valor
        except Exception as e:
            lista_ignorados.append({
                "linha": num_linha, "brinco": brinco_raw,
                "motivo": f"Erro ao inserir: {str(e)[:120]}"
            })

    # Lançamento de compra agregado (consolida o gasto da importação inteira)
    compra_id = None
    if gerar_compra_agregada and importados > 0:
        valor_unit_medio = round(soma_valores / importados, 2)
        try:
            row_compra = supabase.table("compras").insert({
                "fornecedor":  fornecedor,
                "data":        data_compra_iso,
                "descricao":   f"Importação de {importados} animais (carga em massa)",
                "valor_unit":  valor_unit_medio,
                "quantidade":  importados,
                "valor_total": round(soma_valores, 2),
                "mes":         dt_compra.month,
                "ano":         dt_compra.year,
            }).execute().data[0]
            compra_id = row_compra["id"]
        except Exception as e:
            print(f"[importar_animais] aviso: falhou ao gravar lançamento de compra: {e}")

    # Log da importação. try/except defensivo: se a tabela importacoes_animais
    # ainda não foi criada no Supabase do ambiente, a importação real não falha.
    importacao_id = None
    try:
        row_imp = supabase.table("importacoes_animais").insert({
            "fazenda_id":   fazenda_id_final,
            "nome_arquivo": nome,
            "total_linhas": int(len(df)),
            "importados":   importados,
            "ignorados":    len(lista_ignorados),
            "detalhes":     {"ignorados": lista_ignorados},
        }).execute().data[0]
        importacao_id = row_imp["id"]
    except Exception as e:
        print(f"[importar_animais] aviso: falhou ao gravar log em importacoes_animais: {e}")

    return {
        "importados":      importados,
        "ignorados":       len(lista_ignorados),
        "lista_ignorados": lista_ignorados,
        "compra_id":       compra_id,
        "importacao_id":   importacao_id,
    }


@router.put("/{brinco}")
def atualizar_animal(brinco: str, body: dict):
    rows = supabase.table("animais").select("*").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    animal = rows[0]
    update_data = _clean({k: v for k, v in body.items() if k != "brinco"})
    merged = dict(animal)
    merged.update(update_data)
    _validate_and_fill(merged)
    _calcular_custos(merged)
    update_clean = _clean(update_data)
    supabase.table("animais").update(update_clean).eq("id", animal["id"]).execute()
    result = supabase.table("animais").select("*").eq("id", animal["id"]).limit(1).execute().data[0]
    return _to_out(result)


@router.delete("/{brinco}")
def deletar_animal(brinco: str):
    rows = supabase.table("animais").select("id").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    supabase.table("animais").delete().eq("id", rows[0]["id"]).execute()
    return {"mensagem": "Animal removido com sucesso"}


@router.get("/{brinco}/pesagens")
def pesagens_do_animal(brinco: str):
    rows = supabase.table("animais").select("id").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    data = supabase.table("pesagens").select("*").ilike("brinco", brinco).order("data", desc=True).execute().data
    return [{**r, "data_pesagem": r.get("data"), "peso": r.get("peso_kg")} for r in data]


@router.get("/{brinco}/sanidade")
def sanidade_do_animal(brinco: str):
    rows = supabase.table("animais").select("id").ilike("brinco", brinco).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    return supabase.table("sanidade").select("*").ilike("brinco", brinco).order("data", desc=True).execute().data
