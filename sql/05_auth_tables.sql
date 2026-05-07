-- ============================================================
--  Módulo Auth — DDL Supabase
--  Tabelas: usuarios, sessoes.
--
--  Auth é completamente custom (NÃO usa auth.users do Supabase Auth).
--  Cookie cb_token + tabela sessoes; senha em SHA-256 hex (auth.py:_hash).
--  Token de sessão é uuid4().hex (32 caracteres).
--
--  Pré-requisitos: nenhum.
--  Execute no SQL Editor do Supabase (dashboard.supabase.com)
-- ============================================================


-- 1. USUARIOS ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usuarios (
    id          BIGSERIAL    PRIMARY KEY,
    login       TEXT         NOT NULL,
    senha_hash  TEXT         NOT NULL,           -- SHA-256 hexdigest da senha
    nome        TEXT         NOT NULL,
    perfil      TEXT         NOT NULL DEFAULT 'FUNCIONARIO',
    -- perfil IN ('GESTOR','FUNCIONARIO')
    ativo       BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Login único (case-insensitive — auth.py normaliza com .lower())
CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_login
    ON usuarios (lower(login));

CREATE INDEX IF NOT EXISTS idx_usuarios_ativo ON usuarios (ativo);


-- 2. SESSOES ──────────────────────────────────────────────────
--  expira_em é TIMESTAMPTZ. O código em auth.py serializa via
--  isoformat() na escrita e usa fromisoformat() na leitura.
--  Migração do schema antigo (TEXT) está em
--  sql/migrations/2026_05_07_sessoes_expira_em_timestamptz.sql.
CREATE TABLE IF NOT EXISTS sessoes (
    id          BIGSERIAL    PRIMARY KEY,
    token       TEXT         NOT NULL UNIQUE,    -- uuid4().hex (32 chars)
    usuario_id  BIGINT       NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expira_em   TIMESTAMPTZ  NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessoes_token   ON sessoes (token);
CREATE INDEX IF NOT EXISTS idx_sessoes_usuario ON sessoes (usuario_id);
CREATE INDEX IF NOT EXISTS idx_sessoes_expira  ON sessoes (expira_em);
