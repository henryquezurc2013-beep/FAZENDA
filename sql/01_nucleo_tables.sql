-- ============================================================
--  Módulo Núcleo — DDL Supabase
--  Tabelas base sem dependências: fazendas, pessoas, config.
--  Execute no SQL Editor do Supabase (dashboard.supabase.com)
-- ============================================================


-- 1. FAZENDAS ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fazendas (
    id          BIGSERIAL    PRIMARY KEY,
    nome        TEXT         NOT NULL,
    apelido     TEXT,
    cidade      TEXT,
    uf          TEXT,
    area_ha     NUMERIC(10,2),
    cor         TEXT         NOT NULL DEFAULT '#1B5E20',
    ativo       BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Nome de fazenda único (case-insensitive — código usa busca exata)
CREATE UNIQUE INDEX IF NOT EXISTS idx_fazendas_nome
    ON fazendas (lower(nome));


-- 2. PESSOAS ──────────────────────────────────────────────────
--  Cadastro unificado de clientes, fornecedores e parceiros.
--  Código interno (CLI-NNN, FOR-NNN) é gerado pelo backend.
CREATE TABLE IF NOT EXISTS pessoas (
    id          BIGSERIAL    PRIMARY KEY,
    tipo        TEXT,
    -- tipo IN ('CLIENTE','FORNECEDOR')
    pessoa      TEXT,
    -- pessoa IN ('F','J')   (Física ou Jurídica)
    codigo      TEXT,                          -- ex.: CLI-001, FOR-014
    doc         TEXT,                          -- CPF ou CNPJ
    nome        TEXT         NOT NULL,
    endereco    TEXT,
    bairro      TEXT,
    cidade      TEXT,
    uf          TEXT,
    cep         TEXT,
    telefone    TEXT,
    celular     TEXT,
    obs         TEXT,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Código interno é único quando preenchido
CREATE UNIQUE INDEX IF NOT EXISTS idx_pessoas_codigo
    ON pessoas (codigo)
    WHERE codigo IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pessoas_tipo ON pessoas (tipo);
CREATE INDEX IF NOT EXISTS idx_pessoas_nome ON pessoas (lower(nome));


-- 3. CONFIG ───────────────────────────────────────────────────
--  Configurações chave/valor consultadas pela aplicação.
CREATE TABLE IF NOT EXISTS config (
    chave           TEXT         PRIMARY KEY,
    valor           TEXT,
    atualizado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
