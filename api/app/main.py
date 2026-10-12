import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router
from store import db

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Agent Studio")
origins = os.environ.get("CORS_ORIGINS", "http://127.0.0.1:3000,http://127.0.0.1:3001").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in origins if item.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    db.engine()
