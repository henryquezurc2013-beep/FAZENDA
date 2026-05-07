-- ============================================================
--  Módulo Pastagem — DDL Supabase
--  Tabelas: pastos, piquetes, lotes, lote_animais, manejo_pastagem,
--           medicao_pastagem, adubacao_pastagem, chuva.
--  Pré-requisito: 01_nucleo_tables.sql executado (campo fazenda_id).
--
--  IMPORTANTE: este arquivo cria lote_animais com schema completo
--  (data_entrada, data_saida, fazenda_id). A definição parcial que
--  existia em nutricao_tables.sql §5 foi removida — lote_animais agora
--  vive aqui. confinamento_tables.sql ainda contém um ALTER TABLE
--  ADD COLUMN IF NOT EXISTS status que vira no-op contra este schema.
--  Execute no SQL Editor do Supabase (dashboard.supabase.com)
-- ============================================================


-- 1. PASTOS ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pastos (
    id          BIGSERIAL    PRIMARY KEY,
    fazenda_id  BIGINT       NOT NULL DEFAULT 1,
    nome        TEXT         NOT NULL,
    area_ha     NUMERIC(10,2),
    tipo_capim  TEXT,
    sistema     TEXT,                            -- ROTACIONADO, CONTÍNUO, etc.
    status      TEXT         NOT NULL DEFAULT 'ATIVO',
    obs         TEXT,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Nome de pasto único por instalação (case-insensitive)
CREATE UNIQUE INDEX IF NOT EXISTS idx_pastos_nome
    ON pastos (lower(nome));

CREATE INDEX IF NOT EXISTS idx_pastos_fazenda ON pastos (fazenda_id);


-- 2. PIQUETES ─────────────────────────────────────────────────
--  Subdivisões de um pasto. coordenadas é JSON (array de pontos lat/lng)
--  serializado como TEXT — o backend faz json.loads. cor_mapa/icone_mapa
--  controlam apresentação no Leaflet.
--  semaforo é coluna escrita por registrar_entrada/saida do manejo, mas
--  na leitura é recalculada dinamicamente pelo backend (ver /BUGS.md).
CREATE TABLE IF NOT EXISTS piquetes (
    id                  BIGSERIAL    PRIMARY KEY,
    fazenda_id          BIGINT       NOT NULL DEFAULT 1,
    pasto_id            BIGINT       REFERENCES pastos(id) ON DELETE SET NULL,
    nome                TEXT         NOT NULL,
    area_ha             NUMERIC(10,2),
    tipo_capim          TEXT,
    altura_entrada_cm   NUMERIC(6,2),
    altura_saida_cm     NUMERIC(6,2),
    descanso_alvo_dias  INT,
    tem_bebedouro       BOOLEAN      NOT NULL DEFAULT FALSE,
    tem_cocho           BOOLEAN      NOT NULL DEFAULT FALSE,
    tem_sombra          BOOLEAN      NOT NULL DEFAULT FALSE,
    coordenadas         TEXT,                                -- JSON: array de pontos lat/lng
    cor_mapa            TEXT         NOT NULL DEFAULT '#2E7D32',
    icone_mapa          TEXT         NOT NULL DEFAULT '🌿',
    semaforo            TEXT,                                -- legado escrita-only; ver /BUGS.md
    status              TEXT         NOT NULL DEFAULT 'DISPONIVEL',
    obs                 TEXT,
    criado_em           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_piquetes_pasto   ON piquetes (pasto_id);
CREATE INDEX IF NOT EXISTS idx_piquetes_fazenda ON piquetes (fazenda_id);
CREATE INDEX IF NOT EXISTS idx_piquetes_status  ON piquetes (status);


-- 3. LOTES ────────────────────────────────────────────────────
--  Agrupa animais para manejo (pastagem, nutrição, etc.). data_entrada
--  e data_saida acompanham o ciclo do lote no piquete corrente; os
--  campos ua_total, ua_ha e classificacao são recalculados pelo backend.
CREATE TABLE IF NOT EXISTS lotes (
    id            BIGSERIAL    PRIMARY KEY,
    fazenda_id    BIGINT       NOT NULL DEFAULT 1,
    nome          TEXT         NOT NULL,
    categoria     TEXT,
    descricao     TEXT,
    piquete_id    BIGINT       REFERENCES piquetes(id) ON DELETE SET NULL,
    data_entrada  DATE,
    data_saida    DATE,
    status        TEXT         NOT NULL DEFAULT 'ATIVO',
    -- status IN ('ATIVO','INATIVO')
    ua_total      NUMERIC(8,2),                  -- soma (peso/450) dos membros
    ua_ha         NUMERIC(8,2),                  -- ua_total / piquete.area_ha
    classificacao TEXT,                          -- derivada de ua_ha
    criado_em     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Nome de lote único (case-insensitive)
CREATE UNIQUE INDEX IF NOT EXISTS idx_lotes_nome
    ON lotes (lower(nome));

CREATE INDEX IF NOT EXISTS idx_lotes_piquete ON lotes (piquete_id);
CREATE INDEX IF NOT EXISTS idx_lotes_status  ON lotes (status);
CREATE INDEX IF NOT EXISTS idx_lotes_fazenda ON lotes (fazenda_id);


-- 4. LOTE_ANIMAIS (schema completo) ───────────────────────────
--  Substitui a definição parcial de nutricao_tables.sql §5.
--  Permite o mesmo brinco entrar e sair do mesmo lote várias vezes —
--  data_saida marca a saída e a UNIQUE parcial só vale enquanto a
--  vinculação está ativa (data_saida IS NULL).
CREATE TABLE IF NOT EXISTS lote_animais (
    id            BIGSERIAL    PRIMARY KEY,
    fazenda_id    BIGINT       NOT NULL DEFAULT 1,
    lote_id       BIGINT       NOT NULL REFERENCES lotes(id) ON DELETE CASCADE,
    brinco        TEXT         NOT NULL,
    data_entrada  DATE         NOT NULL,
    data_saida    DATE,
    status        TEXT         NOT NULL DEFAULT 'ATIVO',
    -- status IN ('ATIVO','SAIU')
    criado_em     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lote_animais_lote   ON lote_animais (lote_id);
CREATE INDEX IF NOT EXISTS idx_lote_animais_brinco ON lote_animais (lower(brinco));
CREATE INDEX IF NOT EXISTS idx_lote_animais_aberto ON lote_animais (lote_id, data_saida);

-- Impede duas vinculações simultâneas do mesmo brinco no mesmo lote
CREATE UNIQUE INDEX IF NOT EXISTS idx_lote_animais_unq_aberto
    ON lote_animais (lote_id, lower(brinco))
    WHERE data_saida IS NULL;


-- 5. MANEJO_PASTAGEM ──────────────────────────────────────────
--  Eventos de entrada e saída de lote em piquete (NÃO um stay
--  consolidado em uma linha). O backend cria duas linhas por ciclo:
--  uma com tipo='ENTRADA' e outra com tipo='SAIDA'.
CREATE TABLE IF NOT EXISTS manejo_pastagem (
    id           BIGSERIAL    PRIMARY KEY,
    piquete_id   BIGINT       NOT NULL REFERENCES piquetes(id) ON DELETE CASCADE,
    lote_id      BIGINT       REFERENCES lotes(id) ON DELETE SET NULL,
    data         DATE         NOT NULL,
    tipo         TEXT         NOT NULL,
    -- tipo IN ('ENTRADA','SAIDA')
    qtd_animais  INT,
    altura_cm    NUMERIC(6,2),                   -- altura na entrada ou na saída
    obs          TEXT,
    criado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_manejo_piquete ON manejo_pastagem (piquete_id);
CREATE INDEX IF NOT EXISTS idx_manejo_data    ON manejo_pastagem (data DESC);
CREATE INDEX IF NOT EXISTS idx_manejo_lote    ON manejo_pastagem (lote_id);


-- 6. MEDICAO_PASTAGEM ─────────────────────────────────────────
--  Medições de altura, cobertura e condição do piquete ao longo do tempo.
CREATE TABLE IF NOT EXISTS medicao_pastagem (
    id              BIGSERIAL    PRIMARY KEY,
    piquete_id      BIGINT       NOT NULL REFERENCES piquetes(id) ON DELETE CASCADE,
    data            DATE         NOT NULL,
    altura_cm       NUMERIC(6,2) NOT NULL,
    massa_estimada  NUMERIC(10,2),
    cobertura_pct   NUMERIC(5,2),
    falhas_pct      NUMERIC(5,2),
    planta_invasora TEXT,
    condicao        TEXT,
    responsavel     TEXT,
    obs             TEXT,
    criado_em       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_medicao_piquete ON medicao_pastagem (piquete_id);
CREATE INDEX IF NOT EXISTS idx_medicao_data    ON medicao_pastagem (data DESC);


-- 7. ADUBACAO_PASTAGEM ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS adubacao_pastagem (
    id           BIGSERIAL    PRIMARY KEY,
    piquete_id   BIGINT       NOT NULL REFERENCES piquetes(id) ON DELETE CASCADE,
    data         DATE         NOT NULL,
    produto      TEXT         NOT NULL,
    dose_kg_ha   NUMERIC(10,2),
    custo_total  NUMERIC(12,2),
    responsavel  TEXT,
    obs          TEXT,
    criado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_adubacao_piquete ON adubacao_pastagem (piquete_id);
CREATE INDEX IF NOT EXISTS idx_adubacao_data    ON adubacao_pastagem (data DESC);


-- 8. CHUVA ────────────────────────────────────────────────────
--  Registro pluviométrico. Coluna é mm (não mm_chuva como models.py
--  legado sugere). area é texto livre, default lógico no app: 'Fazenda Geral'.
CREATE TABLE IF NOT EXISTS chuva (
    id          BIGSERIAL    PRIMARY KEY,
    fazenda_id  BIGINT       NOT NULL DEFAULT 1,
    data        DATE         NOT NULL,
    area        TEXT,
    mm          NUMERIC(6,2) NOT NULL,
    obs         TEXT,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chuva_data    ON chuva (data DESC);
CREATE INDEX IF NOT EXISTS idx_chuva_fazenda ON chuva (fazenda_id);
