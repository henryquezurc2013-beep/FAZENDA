from fastapi import APIRouter, Query

from database import supabase

router = APIRouter()


@router.get("")
def get_config():
    rows = supabase.table("config").select("*").execute().data
    return {r["chave"]: r["valor"] for r in rows}


@router.put("/{chave}")
def set_config(chave: str, valor: str = Query(...)):
    existing = supabase.table("config").select("chave").eq("chave", chave).limit(1).execute().data
    if existing:
        supabase.table("config").update({"valor": valor}).eq("chave", chave).execute()
    else:
        supabase.table("config").insert({"chave": chave, "valor": valor}).execute()
    return {"chave": chave, "valor": valor}
