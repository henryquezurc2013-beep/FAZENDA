# Débitos técnicos — Controle Bovino

Inconsistências e bugs encontrados durante a Fase 1 (análise de schema).
Os 4 bugs de severidade **alta** foram corrigidos numa fase posterior
(commits abaixo). Os de severidade média/baixa seguem em backlog.

---

| #  | Arquivo / Linha                                                        | Severidade | Descrição                                                                                                                                                                                                                                                                                |
| -- | ---------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | `rebanho/routers/balanca.py:71,75-79,126,131,135,137-147`              | **alta**   | ✅ CORRIGIDO em `3a7ca83`. Usava Schema B legado em `pesagens` (`data_pesagem`, `peso`, `media_dia_kg`, `ganho_pct`, `mes`, `ano`). Importação CSV falharia com PGRST204. Migrado para Schema A (`data`, `peso_kg`, `gmd`, `dias_periodo`, `ganho_kg`, `fazenda_id`). Inclui também ajuste colateral `pasto` → `pasto_atual` em :126,146 (a coluna real em `animais`). |
| 2  | `rebanho/main.py:230` (em `campo_dados`)                               | **alta**   | ✅ CORRIGIDO em `7645e92`. Usava `gte("data_pesagem", limite30)`; coluna real é `data`. Endpoint `/campo/dados` retornava sempre `sem_pesagem_30d == total_ativos`.                                                                                                                       |
| 3  | `rebanho/routers/fazendas.py:93,123`                                   | **alta**   | ✅ CORRIGIDO em `b5ddf03`. `pesagens.select("data_pesagem").order("data_pesagem", desc=True)` em :93 e leitura `ultima_pes["data_pesagem"]` em :123. `GET /fazendas/{id}/resumo` falhava por coluna inexistente.                                                                          |
| 4  | `rebanho/main.py:202`                                                  | **alta**   | ✅ CORRIGIDO em `e8b504f`. Tabela errada: `supabase.table("planos_nutricionais")` (plural). Tabela canônica é `plano_nutricional` (singular). Endpoint `/campo/dados` retornava 0 planos sempre.                                                                                          |
| 5  | `rebanho/routers/exportacao.py:93`                                     | **média**  | `inseminacoes.order("data_insem", desc=True)` — coluna real é `data`. Export CSV de inseminações falha.                                                                                                                                                                                  |
| 6  | `rebanho/routers/relatorios.py:371`                                    | **média**  | `despesas.select("data,categoria,valor").like("data", f"{ano}-%")` — colunas reais são `vencimento` e `tipo`. Endpoint correspondente falha.                                                                                                                                            |
| 7  | `rebanho/routers/pastagem.py:639,690`                                  | **baixa**  | `piquetes.semaforo` é `UPDATE`-ado mas o valor nunca é lido (semáforo é recalculado sob demanda em `semaforo_piquete()`). Coluna existe no DDL para não quebrar os UPDATEs, mas é morta — candidata a remoção.                                                                          |
| 8  | `rebanho/routers/auth.py:35,58-60`                                     | **baixa**  | `sessoes.expira_em` é TEXT formatado em vez de TIMESTAMPTZ. Postgres compara timestamps melhor que strings; trocar exige `strptime` → `fromisoformat` no Python.                                                                                                                       |
| 9  | `rebanho/models.py` (arquivo inteiro)                                  | **média**  | Importa `from database import Base` que não existe mais (`database.py` virou cliente Supabase puro). Se importado em runtime, quebra. Tem campos divergentes do schema real (`pasto` vs `pasto_atual`, `dias_descanso_alvo` vs `descanso_alvo_dias`, `mm_chuva` vs `mm`, `medicao_pasto` vs `medicao_pastagem`, etc.). Candidato a remoção. |
| 10 | `rebanho/seed.py`                                                      | **baixa**  | Seed legado SQLAlchemy. Os routers já têm seeds idiomáticos (`seed_*()`). Arquivo é morto, candidato a remoção.                                                                                                                                                                          |

---

## Próximos passos sugeridos (fora do escopo desta fase)

- **Colunas corretas** — corrigir nomes em `relatorios.py:371` (`vencimento`, `tipo`) e `exportacao.py:93` (`data`).
- **Limpeza** — avaliar remoção de `piquetes.semaforo`, `models.py` e `seed.py` (todos com indícios fortes de código morto).
- **Tipo correto** — migrar `sessoes.expira_em` para TIMESTAMPTZ junto com ajuste em `auth.py:35`.
