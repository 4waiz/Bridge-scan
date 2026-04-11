import os
import sys


APP_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(APP_ROOT)
BACKEND_DIR = os.path.join(APP_ROOT, "backend")
SHAPE_E_DIR = os.path.join(REPO_ROOT, "shap-e")

for path in (BACKEND_DIR, SHAPE_E_DIR):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

from backend.main import app


__all__ = ["app"]
