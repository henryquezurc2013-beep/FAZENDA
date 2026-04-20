from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import date


def _calc_idade(data_nascimento: Optional[str]):
    if not data_nascimento:
        return 0, 0
    try:
        nasc = date.fromisoformat(data_nascimento)
        hoje = date.today()
        anos = hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
        meses_total = (hoje.year - nasc.year) * 12 + (hoje.month - nasc.month)
        if hoje.day < nasc.day:
            meses_total -= 1
        meses = meses_total % 12
        return anos, meses
    except Exception:
        return 0, 0


# ─── Animal ──────────────────────────────────────────────────────────────────

class AnimalBase(BaseModel):
    brinco: str
    nome: Optional[str] = None
    sexo: Optional[str] = None
    origem: Optional[str] = None
    data_compra: Optional[str] = None
    data_nascimento: str
    raca: Optional[str] = None
    tipo: Optional[str] = None
    qtde_animais: Optional[int] = 1
    status: Optional[str] = None
    pasto: Optional[str] = None
    lote: Optional[str] = None
    obs: Optional[str] = None
    nome_pai: Optional[str] = None
    nome_mae: Optional[str] = None
    data_entrada: Optional[str] = None
    data_desmama: Optional[str] = None
    peso_atual: Optional[float] = None
    data_morte: Optional[str] = None
    motivo_morte: Optional[str] = None
    valor_compra: Optional[float] = None
    custo_kg: Optional[float] = None
    custo_arroba: Optional[float] = None


class AnimalCreate(AnimalBase):
    pass


class AnimalUpdate(BaseModel):
    brinco: Optional[str] = None
    nome: Optional[str] = None
    sexo: Optional[str] = None
    origem: Optional[str] = None
    data_compra: Optional[str] = None
    data_nascimento: Optional[str] = None
    raca: Optional[str] = None
    tipo: Optional[str] = None
    qtde_animais: Optional[int] = None
    status: Optional[str] = None
    pasto: Optional[str] = None
    lote: Optional[str] = None
    obs: Optional[str] = None
    nome_pai: Optional[str] = None
    nome_mae: Optional[str] = None
    data_entrada: Optional[str] = None
    data_desmama: Optional[str] = None
    peso_atual: Optional[float] = None
    data_morte: Optional[str] = None
    motivo_morte: Optional[str] = None
    valor_compra: Optional[float] = None
    custo_kg: Optional[float] = None
    custo_arroba: Optional[float] = None


class AnimalOut(AnimalBase):
    id: int
    ult_cria: Optional[str] = None
    mes_morte: Optional[int] = None
    ano_morte: Optional[int] = None
    criado_em: Optional[str] = None
    idade_anos: int = 0
    idade_meses: int = 0

    @field_validator("idade_anos", mode="before")
    @classmethod
    def calc_anos(cls, v, info):
        anos, _ = _calc_idade(info.data.get("data_nascimento"))
        return anos

    @field_validator("idade_meses", mode="before")
    @classmethod
    def calc_meses(cls, v, info):
        _, meses = _calc_idade(info.data.get("data_nascimento"))
        return meses

    class Config:
        from_attributes = True


# ─── Pesagem ─────────────────────────────────────────────────────────────────

class PesagemBase(BaseModel):
    brinco: str
    data_pesagem: str
    peso: float
    pasto: Optional[str] = None


class PesagemCreate(PesagemBase):
    pass


class PesagemOut(PesagemBase):
    id: int
    ganho_kg: Optional[float] = 0
    ganho_pct: Optional[float] = 0
    media_dia_kg: Optional[float] = 0
    mes: Optional[int] = None
    ano: Optional[int] = None

    class Config:
        from_attributes = True


# ─── Sanidade ────────────────────────────────────────────────────────────────

class SanidadeBase(BaseModel):
    brinco: str
    data: str
    medicamento: str
    quantidade: Optional[float] = None
    unidade: Optional[str] = None
    classificacao: Optional[str] = None
    status: Optional[str] = None
    obs: Optional[str] = None


class SanidadeCreate(SanidadeBase):
    pass


class SanidadeOut(SanidadeBase):
    id: int

    class Config:
        from_attributes = True


class SanidadeGrupo(BaseModel):
    brincos: List[str]
    data: str
    medicamento: str
    quantidade: Optional[float] = None
    unidade: Optional[str] = None
    classificacao: Optional[str] = None
    status: Optional[str] = None
    obs: Optional[str] = None


# ─── Inseminação ─────────────────────────────────────────────────────────────

class InseminacaoBase(BaseModel):
    brinco: str
    data_insem: str
    prenhez: Optional[str] = None
    qtd_crias: Optional[int] = 0
    data_nasc_cria: Optional[str] = None
    status: Optional[str] = None
    obs: Optional[str] = None


class InseminacaoCreate(InseminacaoBase):
    pass


class InseminacaoOut(InseminacaoBase):
    id: int

    class Config:
        from_attributes = True


# ─── Compra ──────────────────────────────────────────────────────────────────

class CompraBase(BaseModel):
    pedido: Optional[str] = None
    lote: Optional[str] = None
    fornecedor: Optional[str] = None
    descricao: Optional[str] = None
    data: str
    valor_unit: Optional[float] = 0
    quantidade: Optional[float] = 1
    obs: Optional[str] = None


class CompraCreate(CompraBase):
    pass


class CompraOut(CompraBase):
    id: int
    valor_total: Optional[float] = 0
    mes: Optional[int] = None
    ano: Optional[int] = None

    class Config:
        from_attributes = True


# ─── Venda ───────────────────────────────────────────────────────────────────

class VendaBase(BaseModel):
    pedido: Optional[str] = None
    lote: Optional[str] = None
    cliente: Optional[str] = None
    descricao: Optional[str] = None
    data: str
    valor_unit: Optional[float] = 0
    quantidade: Optional[float] = 1
    obs: Optional[str] = None


class VendaCreate(VendaBase):
    pass


class VendaOut(VendaBase):
    id: int
    valor_total: Optional[float] = 0
    mes: Optional[int] = None
    ano: Optional[int] = None

    class Config:
        from_attributes = True


# ─── Despesa ─────────────────────────────────────────────────────────────────

class DespesaBase(BaseModel):
    tipo: Optional[str] = None
    descricao: Optional[str] = None
    valor: float
    vencimento: str
    status: Optional[str] = None
    obs: Optional[str] = None


class DespesaCreate(DespesaBase):
    pass


class DespesaOut(DespesaBase):
    id: int
    mes: Optional[int] = None
    ano: Optional[int] = None

    class Config:
        from_attributes = True


# ─── Pessoa ──────────────────────────────────────────────────────────────────

class PessoaBase(BaseModel):
    tipo: Optional[str] = None
    pessoa: Optional[str] = None
    doc: Optional[str] = None
    nome: str
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    cep: Optional[str] = None
    telefone: Optional[str] = None
    celular: Optional[str] = None
    obs: Optional[str] = None


class PessoaCreate(PessoaBase):
    pass


class PessoaOut(PessoaBase):
    id: int
    codigo: Optional[str] = None

    class Config:
        from_attributes = True
