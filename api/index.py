import os
import sys

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REBANHO = os.path.join(_BASE, "rebanho")

if _REBANHO not in sys.path:
    sys.path.insert(0, _REBANHO)

os.chdir(_REBANHO)

from main import app  # noqa: E402  (FastAPI app exposto para Vercel @vercel/python)
