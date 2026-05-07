# Schema Supabase — Controle Bovino

DDLs do banco PostgreSQL (Supabase) que sustentam a aplicação.

Cada arquivo é **idempotente** (`CREATE TABLE IF NOT EXISTS` /
`CREATE INDEX IF NOT EXISTS`) e pode ser re-executado sem efeito colateral.

## Ordem de execução

| #  | Arquivo                       | Tabelas criadas                                                                                                                                                                                  |
| -- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1  | `01_nucleo_tables.sql`        | `fazendas`, `pessoas`, `config`                                                                                                                                                                  |
| 2  | `02_animais_tables.sql`       | `animais`, `pesagens`, `sanidade`, `inseminacoes`                                                                                                                                                |
| 3  | `03_financeiro_tables.sql`    | `compras`, `vendas`, `despesas`                                                                                                                                                                  |
| 4  | `04_pastagem_tables.sql`      | `pastos`, `piquetes`, `lotes`, `lote_animais`, `manejo_pastagem`, `medicao_pastagem`, `adubacao_pastagem`, `chuva`                                                                               |
| 5  | `05_auth_tables.sql`          | `usuarios`, `sessoes`                                                                                                                                                                            |
| 6  | `balanca_tables.sql`          | `importacoes_balanca`                                                                                                                                                                            |
| 7  | `nutricao_tables.sql`         | `suplementos`, `plano_nutricional`, `lancamento_racao`, `estoque_suplemento`                                                                                                                     |
| 8  | `confinamento_tables.sql`     | `ingredientes_dieta`, `dietas_confinamento`, `dieta_ingredientes`, `lotes_confinamento`, `fases_confinamento`, `lancamento_confinamento`, `pesagem_confinamento`, `pesagem_conf_individual`      |

### Por que essa ordem

- **01_nucleo** → base, sem dependências (cria `fazendas`).
- **02_animais** → depende implicitamente de `fazendas` (campo `fazenda_id`).
- **03_financeiro** → independente.
- **04_pastagem** → cria `lotes` e `lote_animais`, que `nutricao` e `confinamento` referenciam.
- **05_auth** → independente.
- **balanca_tables.sql** → independente.
- **nutricao_tables.sql** → faz FK em `lotes(id)` (e usa `lote_animais` em joins lógicos), por isso tem que rodar **depois** do 04.
- **confinamento_tables.sql** → contém um `ALTER TABLE lote_animais ADD COLUMN IF NOT EXISTS status`. Como o 04 já cria `status`, o `ALTER` vira **no-op**. Está mantido para idempotência caso você execute apenas o módulo de confinamento isoladamente.

## Como executar

1. Abra o painel do Supabase do projeto.
2. Menu lateral → **SQL Editor** → **New query**.
3. Para cada arquivo da tabela acima (na ordem):
   1. Abra o `.sql` localmente, copie todo o conteúdo.
   2. Cole no editor SQL do Supabase.
   3. Clique em **RUN** (Ctrl+Enter).
   4. Verifique a mensagem "Success. No rows returned".
4. Cada arquivo roda como uma transação implícita do Postgres — se uma instrução falhar, nada do arquivo é aplicado.

> **Dica:** Você pode colar todos os arquivos juntos numa única query, na ordem acima, e rodar de uma vez. O Supabase aceita scripts grandes.

## Como validar

Depois de rodar todos os arquivos:

```bash
# Da raiz do projeto, com .env (SUPABASE_URL + SUPABASE_KEY) configurado:
python diagnostico_fase1.py
```

Saída esperada: **todas** as tabelas com status `OK` e o resumo final mostrando `missing=0 erro=0` para cada módulo.

Se alguma tabela aparecer como `MISSING`:
- Verifique se o arquivo correspondente foi executado.
- Confirme que a key no `.env` é a `service_role` (a `anon` não enxerga tabelas sem RLS configurado).

## Sobre RLS e seeds

- **RLS (Row Level Security)** *não* faz parte desses DDLs. Vai numa fase separada — depende de decisão sobre adoção de Supabase Auth ou modelo alternativo (auth atual é custom, ver `05_auth_tables.sql`).
- **Seeds de dados** (suplementos, dietas, fazendas iniciais, usuários) rodam automaticamente no startup do app via funções `seed_*()` espalhadas nos routers (`fazendas.py`, `nutricao.py`, `confinamento.py`, `auth.py`). Não precisa rodar nada manual de dados.
