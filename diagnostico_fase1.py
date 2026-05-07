"""Diagnóstico Fase 1: schema atual no Supabase vs schema esperado.
Roda local com a service_role do .env. Não modifica nada — só lê.
"""
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# (tabela, modulo)  — nomes exatos usados no código (rebanho/routers/*.py)
EXPECTED = [
    # núcleo
    ("fazendas", "fazendas"),
    ("animais", "animais"),
    ("pesagens", "pesagem"),
    ("sanidade", "sanidade"),
    ("inseminacoes", "inseminacao"),
    ("pessoas", "pessoas"),
    ("config", "config"),
    # financeiro
    ("compras", "financeiro"),
    ("vendas", "financeiro"),
    ("despesas", "financeiro"),
    # balança
    ("importacoes_balanca", "balanca"),
    # pastagem
    ("pastos", "pastagem"),
    ("piquetes", "pastagem"),
    ("manejo_pastagem", "pastagem"),
    ("medicao_pastagem", "pastagem"),
    ("adubacao_pastagem", "pastagem"),
    ("chuva", "pastagem"),
    ("lotes", "pastagem"),
    ("lote_animais", "pastagem"),
    # nutrição
    ("suplementos", "nutricao"),
    ("plano_nutricional", "nutricao"),       # tabela canônica (singular)
    ("lancamento_racao", "nutricao"),
    ("estoque_suplemento", "nutricao"),
    # confinamento
    ("ingredientes_dieta", "confinamento"),
    ("dietas_confinamento", "confinamento"),
    ("dieta_ingredientes", "confinamento"),
    ("lotes_confinamento", "confinamento"),
    ("fases_confinamento", "confinamento"),
    ("lancamento_confinamento", "confinamento"),
    ("pesagem_confinamento", "confinamento"),
    ("pesagem_conf_individual", "confinamento"),
    # auth
    ("usuarios", "auth"),
    ("sessoes", "auth"),
]


def probe(table):
    """Retorna (existe, count_aproximado_ou_None, erro)."""
    try:
        # head=True faz HEAD request, count=exact retorna total
        r = sb.table(table).select("*", count="exact", head=True).execute()
        return True, r.count, None
    except Exception as e:
        msg = str(e)
        # tenta extrair só a mensagem útil
        if "Could not find the table" in msg or "does not exist" in msg or "PGRST205" in msg:
            return False, None, "tabela inexistente"
        return False, None, msg[:120]


def main():
    print(f"\nSupabase: {os.environ['SUPABASE_URL']}\n")
    print(f"{'modulo':<14} {'tabela':<28} {'status':<14} {'rows':>8}")
    print("-" * 72)

    by_module = {}
    for table, mod in EXPECTED:
        existe, count, err = probe(table)
        status = "OK" if existe else ("MISSING" if err == "tabela inexistente" else "ERRO")
        rows = "" if count is None else f"{count}"
        print(f"{mod:<14} {table:<28} {status:<14} {rows:>8}"
              + (f"  -- {err}" if err and err != "tabela inexistente" else ""))
        by_module.setdefault(mod, {"ok": 0, "missing": 0, "erro": 0})
        if existe:
            by_module[mod]["ok"] += 1
        elif err == "tabela inexistente":
            by_module[mod]["missing"] += 1
        else:
            by_module[mod]["erro"] += 1

    print("-" * 72)
    print("\nResumo por módulo:")
    for mod, st in by_module.items():
        flag = "OK " if st["missing"] == 0 and st["erro"] == 0 else "!!!"
        print(f"  {flag} {mod:<14} ok={st['ok']:<3} missing={st['missing']:<3} erro={st['erro']}")


if __name__ == "__main__":
    main()
