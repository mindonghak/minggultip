from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routes import router

app = FastAPI(title="Minggultip")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": "minggultip"}

@app.on_event("startup")
def on_startup():
    init_db()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(router)
