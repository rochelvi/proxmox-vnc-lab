import asyncio
import logging
from urllib.parse import urlencode

import httpx
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import VMAssignment
from app.security import decode_access_token

router = APIRouter(prefix="/api/vms", tags=["vnc"])
logger = logging.getLogger(__name__)


async def _upstream_headers(settings) -> dict[str, str]:
    if settings.pve_user and settings.pve_password:
        url = f"https://{settings.pve_host}:{settings.pve_port}/api2/json/access/ticket"
        async with httpx.AsyncClient(verify=settings.pve_verify_ssl) as client:
            response = await client.post(
                url, data={"username": settings.pve_user, "password": settings.pve_password}
            )
            response.raise_for_status()
            ticket = response.json()["data"]["ticket"]
        return {"Cookie": f"PVEAuthCookie={ticket}"}
    if settings.pve_token_id and settings.pve_token_secret:
        return {"Authorization": f"PVEAPIToken={settings.pve_token_id}={settings.pve_token_secret}"}
    raise RuntimeError("Proxmox credentials are not configured")


@router.websocket("/{vmid}/ws")
async def vnc_websocket(websocket: WebSocket, vmid: int) -> None:
    settings = get_settings()
    token = websocket.query_params.get("token")
    port = websocket.query_params.get("port")
    vnc_ticket = websocket.query_params.get("vncticket")
    if not token or not port or not vnc_ticket:
        await websocket.close(code=4401)
        return
    db = SessionLocal()
    try:
        try:
            claims = decode_access_token(token)
            user_id = int(claims["sub"])
        except Exception:
            await websocket.close(code=4401)
            return
        assignment = db.scalar(select(VMAssignment).where(VMAssignment.vmid == vmid))
        if assignment is None or (assignment.user_id != user_id and not _is_admin(db, user_id)):
            await websocket.close(code=4403)
            return
        await websocket.accept()
        headers = await _upstream_headers(settings)
        query = urlencode({"port": port, "vncticket": vnc_ticket})
        upstream_url = (
            f"wss://{settings.pve_host}:{settings.pve_port}/api2/json/nodes/"
            f"{assignment.node}/qemu/{vmid}/vncwebsocket?{query}"
        )
        async with websockets.connect(
            upstream_url,
            additional_headers=headers,
            subprotocols=["binary"],
            ssl=None if settings.pve_verify_ssl else False,
        ) as upstream:
            async def client_to_pve() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        return
                    data = message.get("bytes")
                    if data is None and message.get("text") is not None:
                        data = message["text"].encode()
                    if data is not None:
                        await upstream.send(data)

            async def pve_to_client() -> None:
                while True:
                    data = await upstream.recv()
                    if isinstance(data, str):
                        data = data.encode()
                    await websocket.send_bytes(data)

            tasks = [asyncio.create_task(client_to_pve()), asyncio.create_task(pve_to_client())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                if task.exception() and not isinstance(task.exception(), WebSocketDisconnect):
                    logger.debug("VNC proxy closed: %s", task.exception())
    except Exception:
        logger.info("VNC proxy ended vmid=%s", vmid, exc_info=True)
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        db.close()


def _is_admin(db, user_id: int) -> bool:
    from app.models import User

    user = db.get(User, user_id)
    return bool(user and user.is_admin)
