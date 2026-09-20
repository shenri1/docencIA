from fastapi import FastAPI

from backend.app.api.router import router as api_router
from backend.app.handlers import registrar_exception_handlers

app = FastAPI()
registrar_exception_handlers(app)
app.include_router(api_router)
