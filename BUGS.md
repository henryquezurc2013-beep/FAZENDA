# Débitos técnicos — Controle Bovino

Inconsistências e bugs encontrados durante a Fase 1 (análise de schema).
Os bugs de severidade **alta** (#1–#4) e **média/baixa** (#5–#10) já
foram corrigidos. Os débitos restantes (#11, #12) são novos, surgidos
durante as próprias rodadas de fix.

---

| #  | Arquivo / Linha                                                        | Severidade | Descrição                                                                                                                                                                                                                                                                                |
| -- | ---------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | `rebanho/routers/balanca.py:71,75-79,126,131,135,137-147`              | **alta**   | ✅ CORRIGIDO em `3a7ca83`. Usava Schema B legado em `pesagens` (`data_pesagem`, `peso`, `media_dia_kg`, `ganho_pct`, `mes`, `ano`). Importação CSV falharia com PGRST204. Migrado para Schema A (`data`, `peso_kg`, `gmd`, `dias_periodo`, `ganho_kg`, `fazenda_id`). Inclui também ajuste colateral `pasto` → `pasto_atual` em :126,146 (a coluna real em `animais`). |
| 2  | `rebanho/main.py:230` (em `campo_dados`)                               | **alta**   | ✅ CORRIGIDO em `7645e92`. Usava `gte("data_pesagem", limite30)`; coluna real é `data`. Endpoint `/campo/dados` retornava sempre `sem_pesagem_30d == total_ativos`.                                                                                                                       |
| 3  | `rebanho/routers/fazendas.py:93,123`                                   | **alta**   | ✅ CORRIGIDO em `b5ddf03`. `pesagens.select("data_pesagem").order("data_pesagem", desc=True)` em :93 e leitura `ultima_pes["data_pesagem"]` em :123. `GET /fazendas/{id}/resumo` falhava por coluna inexistente.                                                                          |
| 4  | `rebanho/main.py:202`                                                  | **alta**   | ✅ CORRIGIDO em `e8b504f`. Tabela errada: `supabase.table("planos_nutricionais")` (plural). Tabela canônica é `plano_nutricional` (singular). Endpoint `/campo/dados` retornava 0 planos sempre.                                                                                          |
| 5  | `rebanho/routers/exportacao.py:93`                                     | **média**  | ✅ CORRIGIDO em `6dc9ffc`. `order`/`get` usavam coluna inexistente `data_insem`; coluna real é `data`. Trocadas as duas refs (query `.order` e consumer `r.get`) em `/exportacao/inseminacoes`. Cabeçalho "Data Inseminação" do CSV mantido (label de saída, não nome de coluna).         |
| 6  | `rebanho/routers/relatorios.py:371`                                    | **média**  | ✅ CORRIGIDO em `e854607`. `.select` usava `data,categoria,valor` e `.like` filtrava por `data`; colunas reais são `vencimento` (DATE) e `tipo`. Trocadas 3 refs em `despesas_relatorio` (`select`, consumer `d.get(vencimento)`, consumer `d.get(tipo)`). Padrão `.like("vencimento", f"{ano}-%")` mantido para consistência com `compras_relatorio` e `vendas_relatorio` (mesmo arquivo, L350-351). |
| 7  | `rebanho/routers/pastagem.py:639,690`                                  | **baixa**  | ✅ CORRIGIDO em `b726ca3` (Caminho C). Mantidos os 2 UPDATEs e a coluna no DDL — apenas marcados como deprecated com comentário inline. Remoção definitiva (DROP COLUMN + remover UPDATEs) será feita na Fase 3 junto com outras mudanças de schema.                                    |
| 8  | `rebanho/routers/auth.py:35,58-60`                                     | **baixa**  | ✅ CORRIGIDO em `398d0ad`. `expira_em` migrado de TEXT para TIMESTAMPTZ. Mudanças em 4 arquivos: `sql/05_auth_tables.sql` (tipo da coluna + comentário invertido); `sql/migrations/2026_05_07_sessoes_expira_em_timestamptz.sql` (novo); `sql/README.md` (seção explicando migrations one-shot); `rebanho/routers/auth.py` (import `timezone`, `_expira()` usa `isoformat()` em UTC, `get_usuario_atual()` usa `fromisoformat` e `datetime.now(utc)`). Migration executada manualmente no Supabase (TRUNCATE TABLE sessoes + ALTER COLUMN). Sessões ATIVAS truncadas — todos os usuários precisaram relogar. |
| 9  | `rebanho/models.py` (arquivo inteiro)                                  | **média**  | ✅ CORRIGIDO em `3614396`. Arquivo deletado. Confirmado morto: `findstr` global mostrou que `seed.py` era o único import de `models.py` em todo o projeto, e `seed.py` também foi deletado no mesmo commit (Bug #10).                                                                    |
| 10 | `rebanho/seed.py`                                                      | **baixa**  | ✅ CORRIGIDO em `3614396`. Arquivo deletado junto com `models.py` (mesmo commit). Importava `SessionLocal`/`create_tables` que não existem mais em `database.py`, e inseria com Schema B (`data_pesagem`, `peso`, `data_insem`, `mm_chuva`). Os routers já têm seeds idiomáticos `seed_*()`. |
| 11 | Vercel — Environment Variables                                         | **baixa**  | `SUPABASE_SECRET_KEY` ainda não foi adicionada na Vercel. Será necessária quando o código precisar bypassar RLS server-side (Fase 3, ao reativar RLS). Hoje o código só usa `SUPABASE_KEY` (publishable) e não precisa da secret.                                                       |
| 12 | `rebanho/routers/relatorios.py:350-351,371`                            | **baixa**  | ✅ CORRIGIDO em `82a3a7c`. Trocadas 3 ocorrências de `.like("col", f"{ano}-%")` por `.gte().lte()` com intervalo DATE explícito em `relatorios.py:350,351,371`. NOTA: o texto original do bug mencionava 3 funções (`compras_relatorio`, `vendas_relatorio`, `despesas_relatorio`), mas no código atual `compras_relatorio` e `vendas_relatorio` foram fundidas em `financeiro(ano)`. Bug afetava as mesmas linhas, fix aplicado. Texto original: três funções usam `.like(coluna, f"{ano}-%")` contra coluna DATE. Funciona em runtime via cast implícito do PostgREST, mas semanticamente seria mais correto usar `.gte/.lte` com intervalo de DATE. |
| 13 | Todo o app (`rebanho/routers/*.py`)                                    | **CRÍTICA** | ✅ CORRIGIDO em `8b037f4`. Middleware HTTP global adicionado em `rebanho/main.py` (`auth_middleware`) que exige autenticação em todas as rotas exceto lista pública. Lista pública (`_ROTAS_PUBLICAS`): `/login`, `/static`, `/favicon.ico`, `/docs`, `/redoc`, `/openapi.json`, `/auth/login`, `/auth/logout`, `/auth/me`. Match = path exato OU `path.startswith(p + "/")` (defensivo contra colisão `/animais` vs `/animais-page`). OPTIONS (CORS pré-flight) sempre passa direto. Não autenticado: retorna 401 JSON quando `Accept: application/json` OU path em prefixo REST conhecido (`/animais`, `/pesagens`, `/sanidade`, `/inseminacoes`, `/compras`, `/vendas`, `/despesas`, `/pessoas`, `/relatorios`, `/exportar`, `/balanca`, `/pastagem`, `/config`, `/nutricao`, `/fazendas`, `/confinamento`, `/campo/dados`); caso contrário (browser) retorna 302 redirect pra `/login`. Reusa `get_usuario_atual()` existente — sem migração pra Supabase Auth nesta fase. Routers individuais e `auth.py` não foram tocados. Originalmente descoberto durante revisão do commit `8c37ade`. |
| 14 | `rebanho/routers/balanca.py:13` (`_BRINCO_COLS`)                       | **alta**   | ✅ CORRIGIDO em `2858392`. Balança TRU-TEST S3 exporta planilha com coluna `IDV` (Identificação Visual). `_BRINCO_COLS` original (`{"animal id", "animal_id", "tag id", "tag_id", "brinco", "id", "animais"}`) não reconhecia `IDV` — `_detect_col` retornava None e `/balanca/importar` levantava 400 "Colunas obrigatórias não encontradas." independente do conteúdo do arquivo. Adicionados: `idv`, `eid`, `vid`, `ear tag`, `tag`. Cobre TRU-TEST e variantes sem virar catch-all permissivo. `_PESO_COLS` e `_DATA_COLS` já cobrem `Peso`/`Data` da S3; `_DATE_FMTS` já aceita formato BR `%d/%m/%Y`. Descoberto em uso real, fora da Fase 1. |
| 15 | `rebanho/routers/balanca.py` + `rebanho/templates/balanca.html`        | **FEATURE** | ✅ ENTREGUE em `6e512e0` (backend) e `9845b3a` (UI). **Estratégia B**: balança auto-cadastra animais cujo brinco não existe em `animais`, em vez de pular. Defaults configuráveis na tela: sexo, raça, tipo, origem (com defaults `MACHO/NELORE/GARROTE/COMPRA`). `cadastrar_novos` checkbox default ON; `valor_medio` e `fornecedor` opcionais — se valor_medio informado, gera 1 lançamento agregado em `/compras` com `valor_total = novos × valor_medio`. `data_compra` do animal = data da pesagem; `data_nascimento` = data_compra − 240 dias. Resultado da importação ganha 5º contador "CADASTRADOS". Mudança de design solicitada após uso real do app — fluxo da fazenda é cadastrar animal novo no momento da primeira pesagem, não pré-cadastro manual. |
| 16 | `rebanho/main.py` (`_ROTAS_PUBLICAS`)                                  | **média**  | ✅ CORRIGIDO em `834244c`. Defesa em profundidade: `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` desabilita os 3 endpoints no nível do framework, e as 3 entradas foram removidas de `_ROTAS_PUBLICAS` em `rebanho/main.py`. Schema da API não é mais acessível mesmo por bypass do middleware. Texto original: `/docs`, `/redoc` e `/openapi.json` (auto-docs do FastAPI) estão na lista pública do middleware de auth para facilitar desenvolvimento. Em DEV é aceitável, mas em produção expõe schema completo da API a qualquer requisição não autenticada — atacante consegue inventário de endpoints e tipos sem credenciais. Originado durante a correção do bug #13. |
| 17 | `rebanho/templates/campo.html` (`.btn-logout` reusado por 🔍 e Sair)   | **baixa**  | Botões "🔍 Buscar" e "Sair" na topbar do `/campo` têm altura ~24-30px (touch target abaixo dos 44px recomendados). Funcional mas risco de mistap em campo. **Fix:** aumentar tamanho dos botões da topbar quando atacar redesenho UX (Plano 2 — pós validação com vaqueiro real). Originado durante o commit 7 do Plano 1 (busca por brinco). |
| 18 | `rebanho/templates/campo.html` (form de Ração)                         | **alta**   | ✅ CORRIGIDO em `0f162bf`. Form da aba Ração no `/campo` era DUMMY: `registrarRacao()` só fazia `toast('Lançamento registrado!')` e descartava o submit. Comentário inline admitia que faltava `plano_id` no `/campo/dados`. Vaqueiro achava que tinha registrado, não tinha — perda silenciosa de dados em uso real. Fix: carrega `/nutricao/planos?status=ATIVO` em adição ao `/campo/dados` pra ter `plano_id` real no select; submit chama `POST /nutricao/lancamentos`. ZERO backend change. Descoberto durante a investigação do Plano 1. |
| 19 | `rebanho/templates/campo.html` (form de Confinamento, path)            | **alta**   | ✅ CORRIGIDO em `7087914`. Form chamava `POST /confinamento/lotes/{id}/lancamentos` — path inexistente. Rota real é `POST /confinamento/lancamentos` (sem `/lotes/{id}/`); `lote_conf_id` vai no body. Catch genérico do JS engolia o 404. Fix: troca de URL no `fetch`. Descoberto durante a investigação do Plano 1. |
| 20 | `rebanho/templates/campo.html` (form de Confinamento, `fase_id`)       | **alta**   | ✅ CORRIGIDO em `7087914` (mesmo commit que #19). `fase_id` estava hardcoded em `1`. Lotes não em fase 1 (Adaptação) geravam lançamentos na fase errada — corrompendo cálculo de custo e MS por fase. Fix: resolver fase ativa antes do POST via `GET /confinamento/lotes/{id}/fases` + filtro JS por `status === 'ATIVA'`. Se nenhuma ativa, toast claro antes do POST. Descoberto durante a investigação do Plano 1. |
| 21 | `rebanho/routers/balanca.py:166` + `rebanho/routers/animais.py:42`     | **baixa**  | ✅ CORRIGIDO em `00c0c62`. `data_nascimento = data_compra - 240d` estava em 2 lugares: `_DATA_NASCIMENTO_OFFSET_DIAS = 240` privada em `animais.py` (reusada no POST `/animais/importar`) e literal `240` hardcoded em `balanca.py` (auto-cadastro da feature #15). Extraído para `rebanho/constants.py` como `DATA_NASCIMENTO_OFFSET_DIAS`. Ambos os routers importam `from constants import ...` (cwd do projeto é `rebanho/`, não a raiz — atestado por `iniciar.bat` e `api/index.py`). |
| 22 | `rebanho/routers/auth.py:27-39` + `rebanho/main.py:81,237,249`         | **baixa**  | ✅ CORRIGIDO em `00a8f12`. Função fazia 2 roundtrips Supabase (SELECT em `sessoes` + SELECT em `usuarios`) e ainda era re-chamada nos handlers `/campo` e `/campo/dados` (4 roundtrips/request nesses endpoints). Fix em duas frentes: (A) JOIN via PostgREST `select="*,usuarios(*)"` aproveitando FK `sessoes.usuario_id → usuarios(id)` — caminho normal passa de 2 para 1 roundtrip; (B) cache por request em `request.state.usuario_atual` setado no `auth_middleware`, handlers leem com `getattr(request.state, "usuario_atual", None)` defensivo. Endpoints `/campo*` passam de 4 para 2 roundtrips por request; demais autenticados passam de 2 para 1. Comentário inline em `auth.py` alerta que JOIN depende do nome `usuarios` da FK. |

---

## Próximos passos sugeridos (fora do escopo desta fase)

Todos os bugs da Fase 1 (#1–#10) e os surgidos em uso real (#14) foram
corrigidos. Feature #15 (auto-cadastro via balança) entregue. Bug #13
(endpoints sem auth, severidade **CRÍTICA**) fechado por middleware
global em `8b037f4`. Plano 1 (app do vaqueiro online) entregue,
incluindo correção dos bugs #18–#20 descobertos durante a investigação.
Débitos restantes: **#11** (Vercel env, só relevante quando reativar
RLS na Fase 3). Demais débitos da Fase 1 (#12, #16) foram resolvidos
em sessão de limpeza. **#17** (touch target da topbar) foi parcialmente
resolvido no Plano 2.1 (`b5c00e4`) — `.btn-logout` agora tem
`min-height: 44px`.

---

## Plano 1 — App do Vaqueiro (Online)

Entregue em 7 commits cobrindo as 6 operações do vaqueiro no `/campo`
(antes só pesagem funcionava de verdade):

- `0f162bf` fix(campo): conserta form de Ração que era dummy (#18)
- `7087914` fix(campo): path correto + fase ativa em Confinamento (#19, #20)
- `f370b17` feat(campo): aba Pasto ganha form de medição
- `038db8c` refactor(campo): aba Pesagem vira "Animais" com sub-tabs Pesar/Medicar/Morte
- `6c5a47a` feat(campo): sub-tab Medicar (sanidade)
- `1c1c3cf` feat(campo): sub-tab Morte com modal de confirmação
- `2e237a7` feat(campo): busca de animal por brinco (botão 🔍 na topbar)

Operações cobertas: ⚖️ pesagem, 🌾 ração, 🏗️ confinamento, 📏 medição
de pasto, 💉 sanidade, ⚠️ morte, 🔍 busca por brinco. Cada submit
chama endpoint REST existente; ZERO mudança em backend.

**Próximo passo:** validação com vaqueiro real por 1 semana antes de
atacar o **Plano 2** (redesenho UX pós-uso real) ou PWA offline.
Débitos visíveis hoje: #17 (touch target da topbar).

---

## Plano 2 — Redesenho UX (parcial)

Entregue em 2 commits:
- `b5c00e4` Plano 2.1 — higiene CSS: viewport sem maximum-scale,
  touch targets ≥44px (resolve parcialmente #17), override
  mobile-friendly em `#sec-racao` e `#sec-conf`, `.c-top-sub`
  11px → 13px, CSS morto removido, classe `.btn-danger` criada
- `db5262e` Plano 2.2 — menu inferior fixo: tabs do topo
  substituídas por `<nav class="c-bottom-nav">` com 4 itens
  (ícone + label), IDs `tab-{pasto,racao,conf,animais}`
  preservados (zero JS tocado), suporte a `safe-area-inset-bottom`

Decisão de processo: validação com vaqueiro real (Fase 1
original) pulada conscientemente. Próxima sub-fase candidata
é Plano 2.3 (cores/contraste pra sol forte) — essa SIM precisa
de validação outdoor antes.

---

## Limpeza de dívida técnica (sessão 2026-05-09)

Entregue em 4 commits após Plano 2:
- `834244c` resolve #16 (/docs em produção)
- `82a3a7c` resolve #12 (refactor SQL relatórios)
- `00c0c62` resolve #21 (constante 240d duplicada)
- `00a8f12` resolve #22 (get_usuario_atual roundtrips)
