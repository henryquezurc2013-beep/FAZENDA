# Débitos técnicos — Controle Bovino

Inconsistências e bugs encontrados durante a Fase 1 (análise de schema).
**Não foram corrigidos** porque o escopo da Fase 1/2 é só DDL — o código
Python ficou intocado por contrato (exceto o ajuste pontual em
`diagnostico_fase1.py`).

---

| #  | Arquivo / Linha                          | Severidade | Descrição                                                                                                                                                                                                              |
| -- | ---------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | `rebanho/routers/balanca.py:71,131,137-148` | **alta**   | Usa Schema B legado em `pesagens` (`data_pesagem`, `peso`, `media_dia_kg`, `ganho_pct`, `mes`, `ano`). Nenhuma dessas colunas existe no schema canônico A; importação CSV vai falhar com PGRST204 ao bater no PostgREST. |
| 2  | `rebanho/main.py:231` (em `campo_dados`) | **alta**   | Mesmo Schema B legado: `pesagens.select("brinco").gte("data_pesagem", limite30)`. Coluna real é `data`. Endpoint `/campo/dados` retorna sempre `sem_pesagem_30d == total_ativos`.                                       |
| 3  | `rebanho/routers/fazendas.py:93`         | **alta**   | Mesmo Schema B legado: `pesagens.select("data_pesagem").order("data_pesagem", desc=True)`. `GET /fazendas/{id}/resumo` falha com erro de coluna inexistente.                                                            |
| 4  | `rebanho/main.py:202`                    | **alta**   | Tabela errada: `supabase.table("planos_nutricionais")` (plural). Tabela canônica é `plano_nutricional` (singular). Endpoint `/campo/dados` retorna 0 planos sempre.                                                     |
| 5  | `rebanho/routers/exportacao.py:93`       | **média**  | `inseminacoes.order("data_insem", desc=True)` — coluna real é `data`. Export CSV de inseminações falha.                                                                                                                |
| 6  | `rebanho/routers/relatorios.py:371`      | **média**  | `despesas.select("data,categoria,valor").like("data", f"{ano}-%")` — colunas reais são `vencimento` e `tipo`. Endpoint correspondente falha.                                                                          |
| 7  | `rebanho/routers/pastagem.py:639,690`    | **baixa**  | `piquetes.semaforo` é `UPDATE`-ado mas o valor nunca é lido (semáforo é recalculado sob demanda em `semaforo_piquete()`). Coluna existe no DDL para não quebrar os UPDATEs, mas é morta — candidata a remoção.        |
| 8  | `rebanho/routers/auth.py:35,58-60`       | **baixa**  | `sessoes.expira_em` é TEXT formatado em vez de TIMESTAMPTZ. Postgres compara timestamps melhor que strings; trocar exige `strptime` → `fromisoformat` no Python.                                                       |
| 9  | `rebanho/models.py` (arquivo inteiro)    | **média**  | Importa `from database import Base` que não existe mais (`database.py` virou cliente Supabase puro). Se importado em runtime, quebra. Tem campos divergentes do schema real (`pasto` vs `pasto_atual`, `dias_descanso_alvo` vs `descanso_alvo_dias`, `mm_chuva` vs `mm`, `medicao_pasto` vs `medicao_pastagem`, etc.). Candidato a remoção. |
| 10 | `rebanho/seed.py`                        | **baixa**  | Seed legado SQLAlchemy. Os routers já têm seeds idiomáticos (`seed_*()`). Arquivo é morto, candidato a remoção.                                                                                                        |

---

## Próximos passos sugeridos (fora do escopo desta fase)

- **Schema A em pesagens** — refatorar `balanca.py`, `main.py:_ctx/campo_dados` e `fazendas.py:93` para usar `data`/`peso_kg`/`gmd`.
- **Tabela canônica** — trocar `planos_nutricionais` por `plano_nutricional` em `main.py:202`.
- **Colunas corretas** — corrigir nomes em `relatorios.py:371` (`vencimento`, `tipo`) e `exportacao.py:93` (`data`).
- **Limpeza** — avaliar remoção de `piquetes.semaforo`, `models.py` e `seed.py` (todos com indícios fortes de código morto).
- **Tipo correto** — migrar `sessoes.expira_em` para TIMESTAMPTZ junto com ajuste em `auth.py:35`.
