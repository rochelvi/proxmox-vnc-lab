import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.routers import auth, vms, vnc


@asynccontextmanager
async def lifespan(application: FastAPI):
    del application
    settings = get_settings()
    init_db()
    if settings.jwt_secret == "change-this-secret":
        logging.getLogger(__name__).warning(
            "JWT_SECRET is still the placeholder default; configure a strong secret before deployment"
        )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    application = FastAPI(title="Proxmox VNC Lab", lifespan=lifespan)
    application.include_router(auth.router)
    application.include_router(vms.router)
    application.include_router(vnc.router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.mount("/", StaticFiles(directory="static", html=True), name="static")
    return application


app = create_app()
