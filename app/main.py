from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import engine, Base
from .routes import router

app = FastAPI(title="Minggultip")

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(router)