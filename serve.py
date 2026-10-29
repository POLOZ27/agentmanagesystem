"""生产环境启动：后台任务 + waitress（单进程，主密钥只在这个进程的内存里）。"""
import os
import secrets
from waitress import serve
from app import app, start_jobs, vault

if __name__ == "__main__":
    if not vault.initialized:
        app.config["SETUP_TOKEN"] = secrets.token_urlsafe(16)
        print(f"SETUP_LINK /setup?t={app.config['SETUP_TOKEN']}", flush=True)
    start_jobs()
    serve(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", 8800)), threads=8)
