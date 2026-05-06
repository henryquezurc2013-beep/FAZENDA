from sqlalchemy import Column, Integer, String, Float, Text, Boolean
from database import Base
from datetime import datetime


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Fazenda(Base):
    __tablename__ = "fazendas"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    nome      = Column(String, nullable=False, unique=True)
    apelido   = Column(String)
    cidade    = Column(String)
    uf        = Column(String)
    area_ha   = Column(Float)
    cor       = Column(String, default='#1B5E20')
    ativo     = Column(Boolean, default=True)
    criado_em = Column(String, default=now_str)


class Animal(Base):
    __tablename__ = "animais"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    brinco          = Column(String, nullable=False, unique=True)
    nome            = Column(String)
    sexo            = Column(String)
    origem          = Column(String)
    data_compra     = Column(String)
    data_nascimento = Column(String, nullable=False)
    raca            = Column(String)
    tipo            = Column(String)
    qtde_animais    = Column(Integer, default=1)
    status          = Column(String)
    pasto           = Column(String)
    lote            = Column(String)
    obs             = Column(String)
    nome_pai        = Column(String)
    nome_mae        = Column(String)
    data_entrada    = Column(String)
    data_desmama    = Column(String)
    peso_atual      = Column(Float)
    ult_cria        = Column(String)
    data_morte      = Column(String)
    motivo_morte    = Column(String)
    mes_morte       = Column(Integer)
    ano_morte       = Column(Integer)
    valor_compra    = Column(Float)
    custo_kg        = Column(Float)
    custo_arroba    = Column(Float)
    criado_em       = Column(String, default=now_str)
    fazenda_id      = Column(Integer, default=1)


class Pesagem(Base):
    __tablename__ = "pesagens"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    brinco       = Column(String, nullable=False)
    data_pesagem = Column(String, nullable=False)
    peso         = Column(Float, nullable=False)
    ganho_kg     = Column(Float, default=0)
    ganho_pct    = Column(Float, default=0)
    media_dia_kg = Column(Float, default=0)
    mes          = Column(Integer)
    ano          = Column(Integer)
    pasto        = Column(String)
    fazenda_id   = Column(Integer, default=1)


class Sanidade(Base):
    __tablename__ = "sanidade"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    brinco        = Column(String, nullable=False)
    data          = Column(String, nullable=False)
    medicamento   = Column(String, nullable=False)
    quantidade    = Column(Float)
    unidade       = Column(String)
    classificacao = Column(String)
    status        = Column(String)
    obs           = Column(String)
    fazenda_id    = Column(Integer, default=1)


class Inseminacao(Base):
    __tablename__ = "inseminacoes"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    brinco         = Column(String, nullable=False)
    data_insem     = Column(String, nullable=False)
    prenhez        = Column(String)
    qtd_crias      = Column(Integer, default=0)
    data_nasc_cria = Column(String)
    status         = Column(String)
    obs            = Column(String)
    fazenda_id     = Column(Integer, default=1)


class Compra(Base):
    __tablename__ = "compras"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    pedido      = Column(String)
    lote        = Column(String)
    fornecedor  = Column(String)
    descricao   = Column(String)
    data        = Column(String, nullable=False)
    valor_unit  = Column(Float, default=0)
    quantidade  = Column(Float, default=1)
    valor_total = Column(Float, default=0)
    obs         = Column(String)
    mes         = Column(Integer)
    ano         = Column(Integer)


class Venda(Base):
    __tablename__ = "vendas"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    pedido      = Column(String)
    lote        = Column(String)
    cliente     = Column(String)
    descricao   = Column(String)
    data        = Column(String, nullable=False)
    valor_unit  = Column(Float, default=0)
    quantidade  = Column(Float, default=1)
    valor_total = Column(Float, default=0)
    obs         = Column(String)
    mes         = Column(Integer)
    ano         = Column(Integer)


class Despesa(Base):
    __tablename__ = "despesas"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    tipo       = Column(String)
    descricao  = Column(String)
    valor      = Column(Float, nullable=False)
    vencimento = Column(String, nullable=False)
    status     = Column(String, default="PENDENTE")
    obs        = Column(String)
    mes        = Column(Integer)
    ano        = Column(Integer)


class Pessoa(Base):
    __tablename__ = "pessoas"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    tipo     = Column(String)
    pessoa   = Column(String)
    codigo   = Column(String, unique=True)
    doc      = Column(String)
    nome     = Column(String, nullable=False)
    endereco = Column(String)
    bairro   = Column(String)
    cidade   = Column(String)
    uf       = Column(String)
    cep      = Column(String)
    telefone = Column(String)
    celular  = Column(String)
    obs      = Column(String)


class ImportacaoBalanca(Base):
    __tablename__ = "importacoes_balanca"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    nome_arquivo    = Column(String, nullable=False)
    data_importacao = Column(String, nullable=False)
    total_linhas    = Column(Integer)
    importados      = Column(Integer)
    ignorados       = Column(Integer)
    erros           = Column(Integer)
    detalhes        = Column(Text)


# ── Módulo de Pastagem ────────────────────────────────────────────────

class Pasto(Base):
    __tablename__ = "pastos"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    nome       = Column(String, nullable=False, unique=True)
    area_ha    = Column(Float)
    tipo_capim = Column(String)
    sistema    = Column(String)
    status     = Column(String, default="ATIVO")
    obs        = Column(String)
    fazenda_id = Column(Integer, default=1)


class Piquete(Base):
    __tablename__ = "piquetes"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    pasto_id            = Column(Integer)
    nome                = Column(String, nullable=False)
    area_ha             = Column(Float)
    tipo_capim          = Column(String)
    altura_entrada_cm   = Column(Float)
    altura_saida_cm     = Column(Float)
    dias_descanso_alvo  = Column(Integer)
    tem_bebedouro       = Column(Boolean, default=False)
    tem_cocho           = Column(Boolean, default=False)
    tem_sombra          = Column(Boolean, default=False)
    status              = Column(String, default="DISPONIVEL")
    obs                 = Column(String)
    coordenadas         = Column(Text)
    cor_mapa            = Column(String, default='#2E7D32')
    icone_mapa          = Column(String, default='🌿')
    fazenda_id          = Column(Integer, default=1)


class ManejoPastagem(Base):
    __tablename__ = "manejo_pastagem"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    data_entrada   = Column(String, nullable=False)
    data_saida     = Column(String)
    piquete_id     = Column(Integer)
    lote           = Column(String)
    qtd_animais    = Column(Integer)
    peso_medio_kg  = Column(Float)
    ua_total       = Column(Float)
    altura_entrada = Column(Float)
    altura_saida   = Column(Float)
    dias_ocupacao  = Column(Integer)
    dias_descanso  = Column(Integer)
    condicao_pasto = Column(String)
    ganho_total_kg = Column(Float)
    ganho_ha_kg    = Column(Float)
    obs            = Column(String)
    fazenda_id     = Column(Integer, default=1)


class MedicaoPasto(Base):
    __tablename__ = "medicao_pasto"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    data            = Column(String, nullable=False)
    piquete_id      = Column(Integer)
    altura_cm       = Column(Float, nullable=False)
    massa_estimada  = Column(Float)
    cobertura_pct   = Column(Float)
    falhas_pct      = Column(Float)
    planta_invasora = Column(String)
    condicao        = Column(String)
    responsavel     = Column(String)
    obs             = Column(String)


class AdubacaoPastagem(Base):
    __tablename__ = "adubacao_pastagem"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    data        = Column(String, nullable=False)
    piquete_id  = Column(Integer)
    produto     = Column(String, nullable=False)
    dose_kg_ha  = Column(Float)
    custo_total = Column(Float)
    responsavel = Column(String)
    obs         = Column(String)
    fazenda_id  = Column(Integer, default=1)


class Chuva(Base):
    __tablename__ = "chuva"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    data       = Column(String, nullable=False)
    area       = Column(String)
    mm_chuva   = Column(Float, nullable=False)
    obs        = Column(String)
    fazenda_id = Column(Integer, default=1)


class Lote(Base):
    __tablename__ = "lotes"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    nome          = Column(String, nullable=False, unique=True)
    categoria     = Column(String)
    descricao     = Column(String)
    piquete_id    = Column(Integer)
    status        = Column(String, default="ATIVO")
    ua_total      = Column(Float, default=0)
    ua_ha         = Column(Float)
    classificacao = Column(String)
    criado_em     = Column(String, default=now_str)
    fazenda_id    = Column(Integer, default=1)


class LoteAnimal(Base):
    __tablename__ = "lote_animais"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    lote_id      = Column(Integer, nullable=False)
    brinco       = Column(String, nullable=False)
    data_entrada = Column(String, nullable=False)
    data_saida   = Column(String)
    status       = Column(String, default="ATIVO")
    fazenda_id   = Column(Integer, default=1)


class LotePasto(Base):
    __tablename__ = "lotes_pasto"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    data           = Column(String, nullable=False)
    lote           = Column(String, nullable=False)
    piquete_id     = Column(Integer)
    qtd_cabecas    = Column(Integer)
    peso_medio_kg  = Column(Float)
    categoria      = Column(String)
    data_entrada   = Column(String)
    previsao_saida = Column(String)
    status         = Column(String, default="ATIVO")


# ── Módulo de Confinamento ────────────────────────────────────────────

class IngredienteDieta(Base):
    __tablename__ = "ingredientes_dieta"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    nome         = Column(String, nullable=False, unique=True)
    tipo         = Column(String, nullable=False)  # VOLUMOSO|CONCENTRADO|MINERAL|ADITIVO
    pct_ms       = Column(Float, nullable=False)
    energia_mcal = Column(Float)
    proteina_pct = Column(Float)
    preco_kg     = Column(Float, nullable=False)
    unidade      = Column(String, default='kg')
    ativo        = Column(Boolean, default=True)
    obs          = Column(String)


class DietaConfinamento(Base):
    __tablename__ = "dietas_confinamento"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    nome         = Column(String, nullable=False, unique=True)
    fase         = Column(String, nullable=False)  # ADAPTACAO|CRESCIMENTO|TERMINACAO|MANUTENCAO
    duracao_dias = Column(Integer)
    obs          = Column(String)
    ativo        = Column(Boolean, default=True)


class DietaIngrediente(Base):
    __tablename__ = "dieta_ingredientes"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    dieta_id       = Column(Integer, nullable=False)
    ingrediente_id = Column(Integer, nullable=False)
    kg_cab_dia     = Column(Float, nullable=False)
    ordem          = Column(Integer, default=0)


class LoteConfinamento(Base):
    __tablename__ = "lotes_confinamento"
    id                 = Column(Integer, primary_key=True, autoincrement=True)
    fazenda_id         = Column(Integer, default=1)
    nome               = Column(String, nullable=False)
    data_entrada       = Column(String, nullable=False)
    data_saida_real    = Column(String)
    qtd_animais        = Column(Integer, nullable=False)
    peso_medio_entrada = Column(Float, nullable=False)
    peso_alvo_saida    = Column(Float, nullable=False)
    valor_compra_cab   = Column(Float, nullable=False)
    frete_entrada      = Column(Float, default=0)
    frete_saida        = Column(Float, default=0)
    mao_obra_cab_dia   = Column(Float, default=0)
    outros_custos      = Column(Float, default=0)
    preco_arroba_venda = Column(Float)
    rc_estimado_pct    = Column(Float, default=54.0)
    rc_real_pct        = Column(Float)
    status             = Column(String, default='ATIVO')
    obs                = Column(String)


class FaseConfinamento(Base):
    __tablename__ = "fases_confinamento"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    lote_conf_id     = Column(Integer, nullable=False)
    dieta_id         = Column(Integer, nullable=False)
    fase             = Column(String, nullable=False)
    data_inicio      = Column(String, nullable=False)
    data_fim         = Column(String)
    duracao_prevista = Column(Integer)
    status           = Column(String, default='ATIVA')
    obs              = Column(String)


class LancamentoConfinamento(Base):
    __tablename__ = "lancamento_confinamento"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    lote_conf_id     = Column(Integer, nullable=False)
    fase_id          = Column(Integer, nullable=False)
    data             = Column(String, nullable=False)
    qtd_fornecida_kg = Column(Float, nullable=False)
    qtd_planejada_kg = Column(Float)
    ms_fornecida_kg  = Column(Float)
    custo_real       = Column(Float)
    responsavel      = Column(String)
    obs              = Column(String)


class PesagemConfinamento(Base):
    __tablename__ = "pesagem_confinamento"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    lote_conf_id  = Column(Integer, nullable=False)
    data          = Column(String, nullable=False)
    peso_medio_kg = Column(Float, nullable=False)
    qtd_animais   = Column(Integer)
    gmd_periodo   = Column(Float)
    ca_periodo    = Column(Float)
    cms_cab_dia   = Column(Float)
    responsavel   = Column(String)
    obs           = Column(String)


class PesagemConfIndividual(Base):
    __tablename__ = "pesagem_conf_individual"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    lote_conf_id = Column(Integer, nullable=False)
    brinco       = Column(String, nullable=False)
    data         = Column(String, nullable=False)
    peso_kg      = Column(Float, nullable=False)
    gmd_periodo  = Column(Float)
    dias_periodo = Column(Integer)
    responsavel  = Column(String)
    obs          = Column(String)


class Config(Base):
    __tablename__ = "config"

    chave = Column(String, primary_key=True)
    valor = Column(String)


class Suplemento(Base):
    __tablename__ = "suplementos"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    nome       = Column(String, nullable=False, unique=True)
    tipo       = Column(String, nullable=False)
    fabricante = Column(String)
    preco_kg   = Column(Float, nullable=False)
    pct_min    = Column(Float)
    pct_max    = Column(Float)
    g_min_fixo = Column(Float)
    g_max_fixo = Column(Float)
    objetivo   = Column(String)
    ativo      = Column(Boolean, default=True)
    obs        = Column(String)


class PlanoNutricional(Base):
    __tablename__ = "plano_nutricional"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    lote_id       = Column(Integer, nullable=False)
    suplemento_id = Column(Integer, nullable=False)
    data_inicio   = Column(String, nullable=False)
    data_fim      = Column(String)
    qtd_animais   = Column(Integer, nullable=False)
    peso_medio_kg = Column(Float, nullable=False)
    preco_kg_snap = Column(Float, nullable=False)
    consumo_min_g = Column(Float)
    consumo_max_g = Column(Float)
    consumo_med_g = Column(Float)
    custo_dia_est = Column(Float)
    custo_mes_est = Column(Float)
    status        = Column(String, default="ATIVO")
    obs           = Column(String)
    fazenda_id    = Column(Integer, default=1)


class LancamentoRacao(Base):
    __tablename__ = "lancamento_racao"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    plano_id         = Column(Integer, nullable=False)
    lote_id          = Column(Integer, nullable=False)
    suplemento_id    = Column(Integer, nullable=False)
    data             = Column(String, nullable=False)
    qtd_fornecida_kg = Column(Float, nullable=False)
    qtd_planejada_kg = Column(Float)
    diferenca_kg     = Column(Float)
    custo_real       = Column(Float)
    responsavel      = Column(String)
    obs              = Column(String)
    fazenda_id       = Column(Integer, default=1)


class EstoqueSuplemento(Base):
    __tablename__ = "estoque_suplemento"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    suplemento_id = Column(Integer, nullable=False)
    data          = Column(String, nullable=False)
    tipo_mov      = Column(String, nullable=False)
    quantidade_kg = Column(Float, nullable=False)
    preco_kg      = Column(Float)
    valor_total   = Column(Float)
    fornecedor    = Column(String)
    nf            = Column(String)
    obs           = Column(String)
    fazenda_id    = Column(Integer, default=1)


# ── Autenticação / Modo Campo ─────────────────────────────────────────

class Usuario(Base):
    __tablename__ = "usuarios"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    login      = Column(String, nullable=False, unique=True)
    senha_hash = Column(String, nullable=False)
    nome       = Column(String, nullable=False)
    perfil     = Column(String, nullable=False, default='FUNCIONARIO')  # GESTOR|FUNCIONARIO
    ativo      = Column(Boolean, default=True)
    criado_em  = Column(String, default=now_str)


class Sessao(Base):
    __tablename__ = "sessoes"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    token      = Column(String, nullable=False, unique=True)
    usuario_id = Column(Integer, nullable=False)
    criado_em  = Column(String, default=now_str)
    expira_em  = Column(String, nullable=False)
