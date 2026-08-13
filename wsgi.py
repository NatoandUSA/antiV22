"""WSGI entry point for production deployments (e.g. Gunicorn under systemd)."""
import os
from pathlib import Path
from dotenv import load_dotenv
from src.web import build_app

load_dotenv()

secret = os.getenv("APP_SECRET_KEY") or os.getenv("WEB_SECRET")
if not secret:
    keyfile = Path("data/.secret_key")
    try:
        secret = keyfile.read_text(encoding="utf-8").strip() if keyfile.exists() else ""
        if not secret:
            secret = os.urandom(24).hex()
            keyfile.parent.mkdir(parents=True, exist_ok=True)
            keyfile.write_text(secret, encoding="utf-8")
    except Exception:
        secret = os.urandom(24).hex()

password = os.getenv("WEB_PASSWORD", "")
app = build_app(password, secret)
