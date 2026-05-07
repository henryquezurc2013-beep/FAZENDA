-- ============================================================
--  Módulo Rebanho — DDL Supabase
--  Tabelas: animais, pesagens, sanidade, inseminacoes.
--  Pré-requisito: 01_nucleo_tables.sql executado (campo fazenda_id).
--  Execute no SQL Editor do Supabase (dashboard.supabase.com)
-- ============================================================


-- 1. ANIMAIS ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS animais (
    id              BIGSERIAL    PRIMARY KEY,
    fazenda_id      BIGINT       NOT NULL DEFAULT 1,
    brinco          TEXT         NOT NULL,
    nome            TEXT,
    tipo            TEXT,
    -- tipo IN ('BEZERRO','BEZERRA','NOVILHA','GARROTE','BOI','TOURO','VACA')
    raca            TEXT,
    sexo            TEXT,
    -- sexo IN ('MACHO','FEMEA')
    data_nascimento DATE,
    data_compra     DATE,
    origem          TEXT,
    -- origem IN ('COMPRA','NASCIMENTO','TROCA')
    valor_compra    NUMERIC(12,2),
    pasto_atual     TEXT,                       -- nome do pasto onde o animal está
    peso_atual      NUMERIC(8,2),
    status          TEXT         NOT NULL DEFAULT 'ATIVO',
    -- status IN ('ATIVO','MORTO','ABATIDO','VENDIDO')
    data_morte      DATE,
    motivo_morte    TEXT,
    custo_kg        NUMERIC(10,2),              -- calculado: valor_compra / peso_atual
    custo_arroba    NUMERIC(10,2),              -- calculado: valor_compra / (peso_atual / 15)
    obs             TEXT,
    criado_em       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Brinco único globalmente (case-insensitive — todos os routers usam ilike)
CREATE UNIQUE INDEX IF NOT EXISTS idx_animais_brinco
    ON animais (lower(brinco));

CREATE INDEX IF NOT EXISTS idx_animais_fazenda ON animais (fazenda_id);
CREATE INDEX IF NOT EXISTS idx_animais_status  ON animais (status);
CREATE INDEX IF NOT EXISTS idx_animais_tipo    ON animais (tipo);


-- 2. PESAGENS ─────────────────────────────────────────────────
--  Schema canônico (Schema A): colunas usadas por pesagem.py / animais.py /
--  relatorios.py / pastagem.py. Há código legado (balanca.py, main.py,
--  fazendas.py) ainda usando data_pesagem/peso/media_dia_kg/ganho_pct/mes/ano
--  — registrado em /BUGS.md. Não validamos UNIQUE(brinco,data) aqui;
--  controle de duplicidade fica no app.
CREATE TABLE IF NOT EXISTS pesagens (
    id            BIGSERIAL     PRIMARY KEY,
    fazenda_id    BIGINT        NOT NULL DEFAULT 1,
    brinco        TEXT          NOT NULL,
    data          DATE          NOT NULL,
    peso_kg       NUMERIC(8,2)  NOT NULL,
    ganho_kg      NUMERIC(8,2)  DEFAULT 0,        -- delta vs pesagem anterior
    gmd           NUMERIC(6,3)  DEFAULT 0,        -- ganho médio diário (kg/dia)
    dias_periodo  INT           DEFAULT 0,        -- dias entre esta pesagem e a anterior
    pasto         TEXT,
    obs           TEXT,
    criado_em     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pesagens_brinco  ON pesagens (lower(brinco));
CREATE INDEX IF NOT EXISTS idx_pesagens_data    ON pesagens (data DESC);
CREATE INDEX IF NOT EXISTS idx_pesagens_fazenda ON pesagens (fazenda_id);


-- 3. SANIDADE ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sanidade (
    id            BIGSERIAL     PRIMARY KEY,
    fazenda_id    BIGINT        NOT NULL DEFAULT 1,
    brinco        TEXT          NOT NULL,
    data          DATE          NOT NULL,
    tipo          TEXT,
    -- tipo IN ('MEDICAMENTO','VACINA','VERMIFUGO')
    produto       TEXT          NOT NULL,
    dose          NUMERIC(10,3),
    via           TEXT,                          -- via de aplicação (oral, injetável, etc.)
    medico_vet    TEXT,
    proxima_data  DATE,                          -- data sugerida de retorno/repique
    custo         NUMERIC(10,2),
    obs           TEXT,
    criado_em     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sanidade_brinco  ON sanidade (lower(brinco));
CREATE INDEX IF NOT EXISTS idx_sanidade_data    ON sanidade (data DESC);
CREATE INDEX IF NOT EXISTS idx_sanidade_fazenda ON sanidade (fazenda_id);


-- 4. INSEMINACOES ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inseminacoes (
    id              BIGSERIAL    PRIMARY KEY,
    fazenda_id      BIGINT       NOT NULL DEFAULT 1,
    brinco_femea    TEXT         NOT NULL,
    data            DATE         NOT NULL,
    tipo            TEXT,                       -- ex.: IATF, monta natural
    touro_brinco    TEXT,
    semen_partida   TEXT,                       -- identificação da partida de sêmen
    tecnico         TEXT,
    resultado       TEXT,
    -- resultado IN ('CONFIRMADA','NAO CONFIRMADA','AGUARDANDO')
    data_resultado  DATE,                       -- data do diagnóstico de prenhez
    data_parto_prev DATE,
    obs             TEXT,
    criado_em       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inseminacoes_brinco  ON inseminacoes (lower(brinco_femea));
CREATE INDEX IF NOT EXISTS idx_inseminacoes_data    ON inseminacoes (data DESC);
CREATE INDEX IF NOT EXISTS idx_inseminacoes_fazenda ON inseminacoes (fazenda_id);
