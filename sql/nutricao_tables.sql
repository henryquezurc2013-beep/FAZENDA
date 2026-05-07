-- ============================================================
--  Módulo de Nutrição — DDL Supabase
--  Pré-requisito: 04_pastagem_tables.sql executado (lotes, lote_animais).
--  Execute no SQL Editor do Supabase (dashboard.supabase.com)
-- ============================================================

-- 1. SUPLEMENTOS ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS suplementos (
    id          BIGSERIAL PRIMARY KEY,
    nome        TEXT        NOT NULL,
    tipo        TEXT        NOT NULL DEFAULT 'SAL_MINERAL',
    -- tipo IN ('SAL_MINERAL','SAL_PROTEINADO','PROT_ENERGETICO',
    --          'RACAO_SEMICONFINADO','VOLUMOSO_SILAGEM','CONCENTRADO_LEITE')
    fabricante  TEXT,
    preco_kg    NUMERIC(10,4) NOT NULL DEFAULT 0,
    -- Dosagem por % do PV (ex: 0.001 = 1 g/kg = 0.1% PV)
    pct_min     NUMERIC(8,6),
    pct_max     NUMERIC(8,6),
    -- Dosagem fixa g/cab/dia (para Sal Mineral)
    g_min_fixo  NUMERIC(8,2),
    g_max_fixo  NUMERIC(8,2),
    objetivo    TEXT,
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    obs         TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_suplementos_nome
    ON suplementos (lower(nome));


-- 2. PLANO NUTRICIONAL ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plano_nutricional (
    id              BIGSERIAL PRIMARY KEY,
    fazenda_id      BIGINT NOT NULL DEFAULT 1,
    lote_id         BIGINT NOT NULL REFERENCES lotes(id) ON DELETE RESTRICT,
    suplemento_id   BIGINT NOT NULL REFERENCES suplementos(id) ON DELETE RESTRICT,
    data_inicio     DATE   NOT NULL DEFAULT CURRENT_DATE,
    data_fim        DATE,
    qtd_animais     INT    NOT NULL DEFAULT 1,
    peso_medio_kg   NUMERIC(8,2) NOT NULL DEFAULT 0,
    preco_kg_snap   NUMERIC(10,4),
    -- Consumo calculado g/cab/dia no momento da criação do plano
    consumo_min_g   NUMERIC(10,3),
    consumo_max_g   NUMERIC(10,3),
    consumo_med_g   NUMERIC(10,3),
    -- Custo estimado
    custo_dia_est   NUMERIC(10,2),
    custo_mes_est   NUMERIC(10,2),
    status          TEXT NOT NULL DEFAULT 'ATIVO',
    -- status IN ('ATIVO','PAUSADO','ENCERRADO')
    obs             TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plano_nut_fazenda ON plano_nutricional(fazenda_id);
CREATE INDEX IF NOT EXISTS idx_plano_nut_lote    ON plano_nutricional(lote_id);
CREATE INDEX IF NOT EXISTS idx_plano_nut_status  ON plano_nutricional(status);


-- 3. LANÇAMENTO DE RAÇÃO ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS lancamento_racao (
    id                BIGSERIAL PRIMARY KEY,
    fazenda_id        BIGINT NOT NULL DEFAULT 1,
    plano_id          BIGINT REFERENCES plano_nutricional(id) ON DELETE RESTRICT,
    lote_id           BIGINT REFERENCES lotes(id) ON DELETE RESTRICT,
    suplemento_id     BIGINT REFERENCES suplementos(id) ON DELETE RESTRICT,
    data              DATE NOT NULL DEFAULT CURRENT_DATE,
    qtd_fornecida_kg  NUMERIC(10,3) NOT NULL,
    qtd_planejada_kg  NUMERIC(10,3),
    diferenca_kg      NUMERIC(10,3),   -- real - planejado
    custo_real        NUMERIC(10,2),
    responsavel       TEXT,
    obs               TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lanc_racao_fazenda ON lancamento_racao(fazenda_id);
CREATE INDEX IF NOT EXISTS idx_lanc_racao_plano   ON lancamento_racao(plano_id);
CREATE INDEX IF NOT EXISTS idx_lanc_racao_data    ON lancamento_racao(data DESC);
CREATE INDEX IF NOT EXISTS idx_lanc_racao_sup     ON lancamento_racao(suplemento_id);

-- Impede duplicata de lançamento por plano/data
CREATE UNIQUE INDEX IF NOT EXISTS idx_lanc_racao_plano_data
    ON lancamento_racao(plano_id, data)
    WHERE plano_id IS NOT NULL;


-- 4. ESTOQUE DE SUPLEMENTO ────────────────────────────────────
CREATE TABLE IF NOT EXISTS estoque_suplemento (
    id             BIGSERIAL PRIMARY KEY,
    fazenda_id     BIGINT NOT NULL DEFAULT 1,
    suplemento_id  BIGINT NOT NULL REFERENCES suplementos(id) ON DELETE RESTRICT,
    data           DATE   NOT NULL DEFAULT CURRENT_DATE,
    tipo_mov       TEXT   NOT NULL DEFAULT 'ENTRADA',
    -- tipo_mov IN ('ENTRADA','SAIDA','AJUSTE')
    quantidade_kg  NUMERIC(10,3) NOT NULL,
    preco_kg       NUMERIC(10,4),
    valor_total    NUMERIC(12,2),
    fornecedor     TEXT,
    obs            TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_est_sup_fazenda ON estoque_suplemento(fazenda_id);
CREATE INDEX IF NOT EXISTS idx_est_sup_sup     ON estoque_suplemento(suplemento_id);
CREATE INDEX IF NOT EXISTS idx_est_sup_data    ON estoque_suplemento(data DESC);


-- §5 (lote_animais) movido para 04_pastagem_tables.sql ───────
--    A definição completa (com data_entrada, data_saida, fazenda_id e
--    UNIQUE parcial) vive agora em 04_pastagem_tables.sql §4. Este
--    arquivo apenas referencia a tabela via FK em plano_nutricional e
--    lancamento_racao acima.
