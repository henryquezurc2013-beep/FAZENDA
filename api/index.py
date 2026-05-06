import os
import sys
import traceback

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REBANHO = os.path.join(_BASE, "rebanho")

if _REBANHO not in sys.path:
    sys.path.insert(0, _REBANHO)

os.chdir(_REBANHO)

try:
    from main import app  # noqa: E402
except Exception as _e:
    _err = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse

    app = FastAPI()

    @app.get("/{full_path:path}")
    async def _debug(full_path: str):
        return PlainTextResponse(
            f"=== IMPORT ERROR ===\n{_err}\n\n"
            f"BASE={_BASE}\nREBANHO={_REBANHO}\nCWD={os.getcwd()}\n"
            f"sys.path[:5]={sys.path[:5]}\n"
            f"ENV: SUPABASE_URL={'SET' if os.environ.get('SUPABASE_URL') else 'MISSING'} "
            f"SUPABASE_KEY={'SET' if os.environ.get('SUPABASE_KEY') else 'MISSING'}\n",
            status_code=500,
        )
