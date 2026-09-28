import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import glossary, meta, projects, segments, services
from .config import get_settings
from .database import init_db
from .services.pipeline import recover_interrupted_jobs

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    recover_interrupted_jobs()
    yield


app = FastAPI(title="AudioSub AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

for module in (meta, projects, segments, glossary, services):
    app.include_router(module.router)
