from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from database import create_tables, SessionLocal
from routers import definicoes, animais, pesagem, sanidade, inseminacao, pessoas, relatorios, exportacao, balanca, pastagem, config as config_router, nutricao
from routers.financeiro import router_compras, router_vendas, router_despesas
from datetime import date, datetime
import uvicorn

app = FastAPI(title="Controle de Rebanho Bovino")

create_tables()
from database import SessionLocal as _SL
from routers.nutricao import seed_nutricao as _seed_nut
_db = _SL(); _seed_nut(_db); _db.close()

app.include_router(definicoes.router, prefix="/definicoes", tags=["Definições"])
app.include_router(animais.router, prefix="/animais", tags=["Animais"])
app.include_router(pesagem.router, prefix="/pesagens", tags=["Pesagens"])
app.include_router(sanidade.router, prefix="/sanidade", tags=["Sanidade"])
app.include_router(inseminacao.router, prefix="/inseminacoes", tags=["Inseminações"])
app.include_router(router_compras, prefix="/compras", tags=["Compras"])
app.include_router(router_vendas, prefix="/vendas", tags=["Vendas"])
app.include_router(router_despesas, prefix="/despesas", tags=["Despesas"])
app.include_router(pessoas.router, prefix="/pessoas", tags=["Pessoas"])
app.include_router(relatorios.router, prefix="/relatorios", tags=["Relatórios"])
app.include_router(exportacao.router, prefix="/exportar", tags=["Exportação"])
app.include_router(balanca.router, prefix="/balanca", tags=["Balança"])
app.include_router(pastagem.router, prefix="/pastagem", tags=["Pastagem"])
app.include_router(config_router.router, prefix="/config", tags=["Config"])
app.include_router(nutricao.router, prefix="/nutricao", tags=["Nutrição"])

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


def _ctx(pagina: str) -> dict:
    from models import Animal, Despesa, Sanidade
    from datetime import timedelta
    db = SessionLocal()
    try:
        hoje_iso = date.today().isoformat()
        limite_180 = (date.today() - timedelta(days=180)).isoformat()

        total_animais = db.query(Animal).filter(Animal.status == "ATIVO").count()

        tem_despesa_vencida = db.query(Despesa).filter(
            Despesa.status == "PENDENTE",
            Despesa.vencimento < hoje_iso
        ).first() is not None

        brincos_com_san = (
            db.query(Sanidade.brinco)
            .filter(Sanidade.data >= limite_180)
            .distinct()
            .subquery()
        )
        alertas_sanidade = db.query(Animal).filter(
            Animal.status == "ATIVO",
            ~Animal.brinco.in_(db.query(brincos_com_san.c.brinco))
        ).count()

    except Exception:
        total_animais = 0
        tem_despesa_vencida = False
        alertas_sanidade = 0
    finally:
        db.close()
    return {
        "pagina": pagina,
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


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return JSONResponse(status_code=404, content={"erro": "Recurso não encontrado"})
    return JSONResponse(status_code=exc.status_code, content={"erro": str(exc.detail)})


if __name__ == "__main__":
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
