import os
import sys

from fastapi import FastAPI

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REBANHO = os.path.join(_BASE, "rebanho")

if _REBANHO not in sys.path:
    sys.path.insert(0, _REBANHO)

os.chdir(_REBANHO)

from main import app as _real_app  # noqa: E402

app: FastAPI = _real_app
