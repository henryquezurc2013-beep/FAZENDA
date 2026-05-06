import os
import httpx
from fastapi import Request
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Forçar HTTP/1.1 no cliente postgrest para evitar RemoteProtocolError com HTTP/2
try:
    _old = supabase.postgrest.session
    _headers = dict(_old.headers)
    _base_url = str(_old.base_url)
    _timeout = _old.timeout
    _old.close()
    supabase.postgrest.session = httpx.Client(
        base_url=_base_url,
        headers=_headers,
        timeout=_timeout,
        http2=False,
    )
except Exception:
    pass


def get_db():
    yield None


def get_fazenda_id(request: Request) -> int:
    fid = (
        request.headers.get("X-Fazenda-ID")
        or request.query_params.get("fazenda_id")
        or "1"
    )
    try:
        return int(fid)
    except (ValueError, TypeError):
        return 1
