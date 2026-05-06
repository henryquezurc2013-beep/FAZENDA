from datetime import date, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from database import supabase
from routers import (
    animais, balanca, config as config_router, confinamento,
    definicoes, exportacao, fazendas, inseminacao, nutricao,
    pastagem, pessoas, pesagem, relatorios, sanidade,
)
from routers.auth import router as auth_router, seed_usuarios as _seed_usuarios
from routers.financeiro import router_compras, router_despesas, router_vendas
from routers.nutricao import seed_nutricao as _seed_nut
from routers.fazendas import seed_fazendas as _seed_faz
from routers.confinamento import seed_confinamento as _seed_conf

app = FastAPI(title="Controle de Rebanho Bovino")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for _seed in (_seed_nut, _seed_faz, _seed_conf, _seed_usuarios):
    try:
        _seed()
    except Exception as _e:
        print(f"[startup] seed {_seed.__name__} ignorado: {_e}")

app.include_router(definicoes.router,    prefix="/definicoes",    tags=["Definições"])
app.include_router(animais.router,       prefix="/animais",        tags=["Animais"])
app.include_router(pesagem.router,       prefix="/pesagens",       tags=["Pesagens"])
app.include_router(sanidade.router,      prefix="/sanidade",       tags=["Sanidade"])
app.include_router(inseminacao.router,   prefix="/inseminacoes",   tags=["Inseminações"])
app.include_router(router_compras,       prefix="/compras",        tags=["Compras"])
app.include_router(router_vendas,        prefix="/vendas",         tags=["Vendas"])
app.include_router(router_despesas,      prefix="/despesas",       tags=["Despesas"])
app.include_router(pessoas.router,       prefix="/pessoas",        tags=["Pessoas"])
app.include_router(relatorios.router,    prefix="/relatorios",     tags=["Relatórios"])
app.include_router(exportacao.router,    prefix="/exportar",       tags=["Exportação"])
app.include_router(balanca.router,       prefix="/balanca",        tags=["Balança"])
app.include_router(pastagem.router,      prefix="/pastagem",       tags=["Pastagem"])
app.include_router(config_router.router, prefix="/config",         tags=["Config"])
app.include_router(nutricao.router,      prefix="/nutricao",       tags=["Nutrição"])
app.include_router(fazendas.router,      prefix="/fazendas",       tags=["Fazendas"])
app.include_router(confinamento.router,  prefix="/confinamento",   tags=["Confinamento"])
app.include_router(auth_router,          prefix="/auth",           tags=["Auth"])

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


def _ctx(pagina: str) -> dict:
    try:
        hoje_iso = date.today().isoformat()
        limite_180 = (date.today() - timedelta(days=180)).isoformat()

        animais_rows = supabase.table("animais").select("brinco").eq("status", "ATIVO").execute().data
        total_animais = len(animais_rows)
        brincos_ativos = {a["brinco"] for a in animais_rows}

        despesa_rows = supabase.table("despesas").select("id").eq("status", "PENDENTE").lt("vencimento", hoje_iso).limit(1).execute().data
        tem_despesa_vencida = len(despesa_rows) > 0

        san_rows = supabase.table("sanidade").select("brinco").gte("data", limite_180).execute().data
        brincos_com_san = {r["brinco"] for r in san_rows}
        alertas_sanidade = sum(1 for b in brincos_ativos if b not in brincos_com_san)

    except Exception:
        total_animais = 0
        tem_despesa_vencida = False
        alertas_sanidade = 0

    return {
        "pagina": pagina,
        "page": pagina,
        "data_atual": date.today().strftime("%d/%m/%Y"),
        "hora_atual": datetime.now().strftime("%H:%M"),
        "total_animais": total_animais,
        "alertas_financeiro": tem_despesa_vencida,
        "alertas_despesas": 1 if tem_despesa_vencida else 0,
        "alertas_sanidade": alertas_sanidade,
    }


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard")
async def page_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context=_ctx("dashboard"))


@app.get("/animais-page")
async def page_animais(request: Request):
    return templates.TemplateResponse(request=request, name="animais.html", context=_ctx("animais"))


@app.get("/pesagem-page")
async def page_pesagem(request: Request):
    return templates.TemplateResponse(request=request, name="pesagem.html", context=_ctx("pesagem"))


@app.get("/sanidade-page")
async def page_sanidade(request: Request):
    return templates.TemplateResponse(request=request, name="sanidade.html", context=_ctx("sanidade"))


@app.get("/inseminacao-page")
async def page_inseminacao(request: Request):
    return templates.TemplateResponse(request=request, name="inseminacao.html", context=_ctx("inseminacao"))


@app.get("/financeiro-page")
async def page_financeiro(request: Request):
    return templates.TemplateResponse(request=request, name="financeiro.html", context=_ctx("financeiro"))


@app.get("/pessoas-page")
async def page_pessoas(request: Request):
    return templates.TemplateResponse(request=request, name="pessoas.html", context=_ctx("pessoas"))


@app.get("/fazendas-page")
async def page_fazendas(request: Request):
    return templates.TemplateResponse(request=request, name="fazendas.html", context=_ctx("fazendas"))


@app.get("/relatorios-page")
async def page_relatorios(request: Request):
    return templates.TemplateResponse(request=request, name="relatorios.html", context=_ctx("relatorios"))


@app.get("/balanca-page")
async def page_balanca(request: Request):
    return templates.TemplateResponse(request=request, name="balanca.html", context=_ctx("balanca"))


@app.get("/pastagem-page")
async def page_pastagem(request: Request):
    return templates.TemplateResponse(request=request, name="pastagem.html", context=_ctx("pastagem"))


@app.get("/nutricao-page")
async def page_nutricao(request: Request):
    return templates.TemplateResponse(request=request, name="nutricao.html", context=_ctx("nutricao"))


@app.get("/confinamento-page")
async def page_confinamento(request: Request):
    return templates.TemplateResponse(request=request, name="confinamento.html", context=_ctx("confinamento"))


@app.get("/login")
async def page_login(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})


@app.get("/campo")
async def page_campo(request: Request):
    from routers.auth import get_usuario_atual
    u = get_usuario_atual(request)
    if not u:
        return RedirectResponse(url="/login")
    ctx = _ctx("campo")
    ctx["usuario_nome"] = u["nome"]
    ctx["usuario_perfil"] = u["perfil"]
    return templates.TemplateResponse(request=request, name="campo.html", context=ctx)


@app.get("/campo/dados")
async def campo_dados(request: Request):
    from routers.auth import get_usuario_atual
    from database import get_fazenda_id

    u = get_usuario_atual(request)
    if not u:
        raise StarletteHTTPException(status_code=401, detail="Não autenticado")

    fid = get_fazenda_id(request)
    hoje = date.today()
    hoje_iso = hoje.isoformat()

    piquetes = supabase.table("piquetes").select("nome,area_ha,status").eq("fazenda_id", fid).limit(10).execute().data
    pastagem_resumo = [
        {"piquete": p["nome"], "area_ha": p.get("area_ha"), "status": p.get("status") or "DISPONIVEL"}
        for p in piquetes
    ]

    planos = supabase.table("planos_nutricionais").select("*").eq("fazenda_id", fid).eq("status", "ATIVO").execute().data
    planos_hoje = []
    for pl in planos:
        if pl.get("data_inicio") and pl["data_inicio"] <= hoje_iso and (not pl.get("data_fim") or pl["data_fim"] >= hoje_iso):
            sup_rows = supabase.table("suplementos").select("nome").eq("id", pl["suplemento_id"]).limit(1).execute().data
            lote_rows = supabase.table("lotes").select("nome").eq("id", pl["lote_id"]).limit(1).execute().data
            planos_hoje.append({
                "lote": lote_rows[0]["nome"] if lote_rows else "—",
                "suplemento": sup_rows[0]["nome"] if sup_rows else "—",
                "consumo_med_g": pl.get("consumo_med_g"),
                "qtd_animais": pl.get("qtd_animais"),
                "custo_dia": pl.get("custo_dia_est"),
            })

    lotes_conf = supabase.table("lotes_confinamento").select("*").eq("fazenda_id", fid).eq("status", "ATIVO").execute().data
    conf_hoje = []
    for lc in lotes_conf:
        ultimo_rows = supabase.table("lancamento_confinamento").select("data").eq("lote_conf_id", lc["id"]).order("data", desc=True).limit(1).execute().data
        ultimo_lanc = ultimo_rows[0] if ultimo_rows else None
        conf_hoje.append({
            "id": lc["id"],
            "nome": lc["nome"],
            "qtd_animais": lc.get("qtd_animais"),
            "ultimo_lancamento": ultimo_lanc["data"] if ultimo_lanc else None,
            "lancou_hoje": (ultimo_lanc["data"] == hoje_iso) if ultimo_lanc else False,
        })

    limite30 = (hoje - timedelta(days=30)).isoformat()
    pesagens_rows = supabase.table("pesagens").select("brinco").gte("data_pesagem", limite30).execute().data
    brincos_pesados = {p["brinco"] for p in pesagens_rows}
    ativos_rows = supabase.table("animais").select("brinco").eq("status", "ATIVO").eq("fazenda_id", fid).execute().data
    sem_pesagem = sum(1 for a in ativos_rows if a["brinco"] not in brincos_pesados)

    return {
        "pastagem": pastagem_resumo,
        "nutricao": planos_hoje,
        "confinamento": conf_hoje,
        "pesagem": {"sem_pesagem_30d": sem_pesagem},
    }


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return JSONResponse(status_code=404, content={"erro": "Recurso não encontrado"})
    return JSONResponse(status_code=exc.status_code, content={"erro": str(exc.detail)})


if __name__ == "__main__":
    import os
    import uvicorn
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
