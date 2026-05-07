-- ============================================================
--  Migration: sessoes.expira_em TEXT → TIMESTAMPTZ
--  Data: 2026-05-07 (bug #8 do BUGS.md)
--
--  Decisao tomada com revisor: limpar sessoes ATIVAS antes do
--  ALTER (todos os usuarios precisam re-logar), trade-off
--  aceito para evitar tentar parsear timestamps no formato
--  antigo.
--
--  Executar UMA UNICA VEZ no SQL Editor do Supabase.
--  Idempotente: ALTER COLUMN ... TYPE TIMESTAMPTZ aplicado
--  contra uma coluna que ja e TIMESTAMPTZ resulta em no-op.
-- ============================================================

TRUNCATE TABLE sessoes;

ALTER TABLE sessoes
    ALTER COLUMN expira_em TYPE TIMESTAMPTZ
    USING expira_em::timestamptz;
