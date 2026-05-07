-- ============================================================
--  Módulo Financeiro — DDL Supabase
--  Tabelas: compras, vendas, despesas.
--  Sem vínculo com fazenda_id (escopo global do app, não por fazenda).
--  Campos mes/ano são denormalizações alimentadas pelo backend a
--  partir da data principal (data ou vencimento).
--  Execute no SQL Editor do Supabase (dashboard.supabase.com)
-- ============================================================


-- 1. COMPRAS ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compras (
    id           BIGSERIAL     PRIMARY KEY,
    pedido       TEXT,
    lote         TEXT,
    fornecedor   TEXT,
    descricao    TEXT,
    data         DATE          NOT NULL,
    valor_unit   NUMERIC(12,4) DEFAULT 0,
    quantidade   NUMERIC(12,3) DEFAULT 1,
    valor_total  NUMERIC(14,2) DEFAULT 0,         -- calculado: valor_unit * quantidade
    mes          INT,                              -- denormalizado de data
    ano          INT,                              -- denormalizado de data
    obs          TEXT,
    criado_em    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compras_data       ON compras (data DESC);
CREATE INDEX IF NOT EXISTS idx_compras_periodo    ON compras (ano, mes);
CREATE INDEX IF NOT EXISTS idx_compras_fornecedor ON compras (lower(fornecedor));


-- 2. VENDAS ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vendas (
    id           BIGSERIAL     PRIMARY KEY,
    pedido       TEXT,
    lote         TEXT,
    cliente      TEXT,
    descricao    TEXT,
    data         DATE          NOT NULL,
    valor_unit   NUMERIC(12,4) DEFAULT 0,
    quantidade   NUMERIC(12,3) DEFAULT 1,
    valor_total  NUMERIC(14,2) DEFAULT 0,         -- calculado: valor_unit * quantidade
    mes          INT,
    ano          INT,
    obs          TEXT,
    criado_em    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vendas_data    ON vendas (data DESC);
CREATE INDEX IF NOT EXISTS idx_vendas_periodo ON vendas (ano, mes);
CREATE INDEX IF NOT EXISTS idx_vendas_cliente ON vendas (lower(cliente));


-- 3. DESPESAS ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS despesas (
    id          BIGSERIAL     PRIMARY KEY,
    tipo        TEXT,
    -- tipo IN ('INSUMOS','FUNCIONÁRIO','TRANSPORTE','INTERNET','OUTROS')
    descricao   TEXT,
    valor       NUMERIC(12,2) NOT NULL,
    vencimento  DATE          NOT NULL,
    status      TEXT          NOT NULL DEFAULT 'PENDENTE',
    -- status IN ('PENDENTE','PAGO')
    mes         INT,                              -- denormalizado de vencimento
    ano         INT,                              -- denormalizado de vencimento
    obs         TEXT,
    criado_em   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_despesas_venc    ON despesas (vencimento);
CREATE INDEX IF NOT EXISTS idx_despesas_status  ON despesas (status);
CREATE INDEX IF NOT EXISTS idx_despesas_periodo ON despesas (ano, mes);
