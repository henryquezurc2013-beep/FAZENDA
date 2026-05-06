-- ============================================================
--  Módulo Balança TRU-TEST S3 — DDL Supabase
--  Execute no SQL Editor do Supabase (dashboard.supabase.com)
-- ============================================================

-- IMPORTACOES_BALANCA ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS importacoes_balanca (
    id               BIGSERIAL    PRIMARY KEY,
    nome_arquivo     TEXT         NOT NULL,
    data_importacao  TEXT         NOT NULL,   -- "YYYY-MM-DD HH:MM:SS"
    total_linhas     INT          NOT NULL DEFAULT 0,
    importados       INT          NOT NULL DEFAULT 0,
    ignorados        INT          NOT NULL DEFAULT 0,
    erros            INT          NOT NULL DEFAULT 0,
    detalhes         TEXT,                    -- JSON com listas de ignorados/erros
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_imp_balanca_data
    ON importacoes_balanca (data_importacao DESC);
