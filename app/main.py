import logging
import logging.config

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.routers import auth, vms, vnc


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    application = FastAPI(title="Proxmox VNC Lab")
    application.include_router(auth.router)
    application.include_router(vms.router)
    application.include_router(vnc.router)

    @application.on_event("startup")
    def startup() -> None:
        init_db()

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.mount("/", StaticFiles(directory="static", html=True), name="static")
    return application


app = create_app()
