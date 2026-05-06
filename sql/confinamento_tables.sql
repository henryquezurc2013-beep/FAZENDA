-- ============================================================
--  Módulo de Confinamento — DDL Supabase
--  Execute no SQL Editor do Supabase (dashboard.supabase.com)
--  Pré-requisito: nutricao_tables.sql já executado (cria lote_animais)
-- ============================================================

-- 0. Ajuste na lote_animais (adicionar status se não existir) ─────────────
ALTER TABLE lote_animais
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ATIVO';


-- 1. INGREDIENTES_DIETA ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ingredientes_dieta (
    id            BIGSERIAL PRIMARY KEY,
    nome          TEXT          NOT NULL,
    tipo          TEXT          NOT NULL DEFAULT 'VOLUMOSO',
    -- tipo IN ('VOLUMOSO','CONCENTRADO','MINERAL','ADITIVO')
    pct_ms        NUMERIC(6,2)  NOT NULL,  -- % matéria seca (1-100)
    energia_mcal  NUMERIC(6,3),            -- Mcal/kg MS (opcional)
    proteina_pct  NUMERIC(6,2),            -- % proteína bruta (opcional)
    preco_kg      NUMERIC(10,4) NOT NULL DEFAULT 0,
    unidade       TEXT          NOT NULL DEFAULT 'kg',
    ativo         BOOLEAN       NOT NULL DEFAULT TRUE,
    obs           TEXT,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ing_dieta_nome
    ON ingredientes_dieta (lower(nome));


-- 2. DIETAS_CONFINAMENTO ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dietas_confinamento (
    id            BIGSERIAL PRIMARY KEY,
    nome          TEXT    NOT NULL,
    fase          TEXT    NOT NULL DEFAULT 'CRESCIMENTO',
    -- fase IN ('ADAPTACAO','CRESCIMENTO','TERMINACAO','MANUTENCAO')
    duracao_dias  INT,
    obs           TEXT,
    ativo         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dieta_conf_nome
    ON dietas_confinamento (lower(nome));


-- 3. DIETA_INGREDIENTES ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dieta_ingredientes (
    id              BIGSERIAL PRIMARY KEY,
    dieta_id        BIGINT        NOT NULL REFERENCES dietas_confinamento(id) ON DELETE CASCADE,
    ingrediente_id  BIGINT        NOT NULL REFERENCES ingredientes_dieta(id) ON DELETE RESTRICT,
    kg_cab_dia      NUMERIC(8,3)  NOT NULL,  -- kg/cab/dia como fornecido
    ordem           INT           NOT NULL DEFAULT 0,
    UNIQUE (dieta_id, ingrediente_id)
);

CREATE INDEX IF NOT EXISTS idx_dieta_ing_dieta ON dieta_ingredientes(dieta_id);
CREATE INDEX IF NOT EXISTS idx_dieta_ing_ing   ON dieta_ingredientes(ingrediente_id);


-- 4. LOTES_CONFINAMENTO ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lotes_confinamento (
    id                  BIGSERIAL     PRIMARY KEY,
    fazenda_id          BIGINT        NOT NULL DEFAULT 1,
    nome                TEXT          NOT NULL,
    data_entrada        DATE          NOT NULL,
    data_saida_real     DATE,
    qtd_animais         INT           NOT NULL DEFAULT 1,
    peso_medio_entrada  NUMERIC(8,2)  NOT NULL DEFAULT 0,
    peso_alvo_saida     NUMERIC(8,2)  NOT NULL DEFAULT 0,
    valor_compra_cab    NUMERIC(10,2) NOT NULL DEFAULT 0,
    frete_entrada       NUMERIC(10,2) NOT NULL DEFAULT 0,
    frete_saida         NUMERIC(10,2)          DEFAULT 0,
    mao_obra_cab_dia    NUMERIC(8,4)           DEFAULT 0,
    outros_custos       NUMERIC(10,2)          DEFAULT 0,
    preco_arroba_venda  NUMERIC(10,2),
    rc_estimado_pct     NUMERIC(6,2)           DEFAULT 54.0,
    rc_real_pct         NUMERIC(6,2),
    status              TEXT          NOT NULL DEFAULT 'ATIVO',
    -- status IN ('ATIVO','ENCERRADO','VENDIDO')
    obs                 TEXT,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lotes_conf_fazenda ON lotes_confinamento(fazenda_id);
CREATE INDEX IF NOT EXISTS idx_lotes_conf_status  ON lotes_confinamento(status);


-- 5. FASES_CONFINAMENTO ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fases_confinamento (
    id                BIGSERIAL    PRIMARY KEY,
    lote_conf_id      BIGINT       NOT NULL REFERENCES lotes_confinamento(id) ON DELETE CASCADE,
    dieta_id          BIGINT       NOT NULL REFERENCES dietas_confinamento(id) ON DELETE RESTRICT,
    fase              TEXT         NOT NULL,
    -- fase IN ('ADAPTACAO','CRESCIMENTO','TERMINACAO','MANUTENCAO')
    data_inicio       DATE         NOT NULL,
    data_fim          DATE,
    duracao_prevista  INT,
    status            TEXT         NOT NULL DEFAULT 'ATIVA',
    -- status IN ('ATIVA','CONCLUIDA')
    obs               TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fases_conf_lote   ON fases_confinamento(lote_conf_id);
CREATE INDEX IF NOT EXISTS idx_fases_conf_status ON fases_confinamento(status);


-- 6. LANCAMENTO_CONFINAMENTO ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lancamento_confinamento (
    id                BIGSERIAL     PRIMARY KEY,
    lote_conf_id      BIGINT        NOT NULL REFERENCES lotes_confinamento(id) ON DELETE RESTRICT,
    fase_id           BIGINT                 REFERENCES fases_confinamento(id) ON DELETE SET NULL,
    data              DATE          NOT NULL,
    qtd_fornecida_kg  NUMERIC(10,3) NOT NULL,
    qtd_planejada_kg  NUMERIC(10,3),
    ms_fornecida_kg   NUMERIC(10,3),
    custo_real        NUMERIC(10,2),
    responsavel       TEXT,
    obs               TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lanc_conf_lote ON lancamento_confinamento(lote_conf_id);
CREATE INDEX IF NOT EXISTS idx_lanc_conf_data ON lancamento_confinamento(data DESC);
CREATE INDEX IF NOT EXISTS idx_lanc_conf_fase ON lancamento_confinamento(fase_id);

-- Evitar dois lançamentos para o mesmo lote no mesmo dia
CREATE UNIQUE INDEX IF NOT EXISTS idx_lanc_conf_lote_data
    ON lancamento_confinamento(lote_conf_id, data);


-- 7. PESAGEM_CONFINAMENTO (média do lote) ────────────────────────────────
CREATE TABLE IF NOT EXISTS pesagem_confinamento (
    id             BIGSERIAL     PRIMARY KEY,
    lote_conf_id   BIGINT        NOT NULL REFERENCES lotes_confinamento(id) ON DELETE CASCADE,
    data           DATE          NOT NULL,
    peso_medio_kg  NUMERIC(8,2)  NOT NULL,
    qtd_animais    INT,
    gmd_periodo    NUMERIC(6,3),   -- kg/dia desde pesagem anterior
    ca_periodo     NUMERIC(6,2),   -- CA desde pesagem anterior
    cms_cab_dia    NUMERIC(6,3),   -- CMS médio no período
    responsavel    TEXT,
    obs            TEXT,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (lote_conf_id, data)
);

CREATE INDEX IF NOT EXISTS idx_pes_conf_lote ON pesagem_confinamento(lote_conf_id);
CREATE INDEX IF NOT EXISTS idx_pes_conf_data ON pesagem_confinamento(data DESC);


-- 8. PESAGEM_CONF_INDIVIDUAL (por brinco dentro do lote) ─────────────────
CREATE TABLE IF NOT EXISTS pesagem_conf_individual (
    id             BIGSERIAL     PRIMARY KEY,
    lote_conf_id   BIGINT        NOT NULL REFERENCES lotes_confinamento(id) ON DELETE CASCADE,
    brinco         TEXT          NOT NULL,
    data           DATE          NOT NULL,
    peso_kg        NUMERIC(8,2)  NOT NULL,
    gmd_periodo    NUMERIC(6,3),
    dias_periodo   INT,
    responsavel    TEXT,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pci_lote   ON pesagem_conf_individual(lote_conf_id);
CREATE INDEX IF NOT EXISTS idx_pci_brinco ON pesagem_conf_individual(brinco);
CREATE INDEX IF NOT EXISTS idx_pci_data   ON pesagem_conf_individual(data DESC);
