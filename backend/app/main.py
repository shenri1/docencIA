from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.router import router as api_router
from backend.app.core.db import engine
from backend.app.handlers import registrar_exception_handlers
from backend.app.models import Base


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # create_all só cria o que falta, não versiona mudanças de schema.
    # Trocar por Alembic antes do primeiro schema em produção.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)
registrar_exception_handlers(app)
app.include_router(api_router)
