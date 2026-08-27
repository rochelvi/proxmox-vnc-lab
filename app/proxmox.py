import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from proxmoxer import ProxmoxAPI
from proxmoxer.core import ResourceException
from requests.exceptions import ConnectionError as RequestsConnectionError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import VMAssignment

logger = logging.getLogger(__name__)


class ProxmoxService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._api = None

    @property
    def api(self):
        if self._api is None:
            if self.settings.pve_token_id and self.settings.pve_token_secret:
                token_parts = self.settings.pve_token_id.split("!", 1)
                if len(token_parts) != 2:
                    raise HTTPException(502, "Invalid PVE_TOKEN_ID")
                self._api = ProxmoxAPI(
                    self.settings.pve_host,
                    port=self.settings.pve_port,
                    user=token_parts[0],
                    token_name=token_parts[1],
                    token_value=self.settings.pve_token_secret,
                    verify_ssl=self.settings.pve_verify_ssl,
                )
            elif self.settings.pve_user and self.settings.pve_password:
                self._api = ProxmoxAPI(
                    self.settings.pve_host,
                    port=self.settings.pve_port,
                    user=self.settings.pve_user,
                    password=self.settings.pve_password,
                    verify_ssl=self.settings.pve_verify_ssl,
                )
            else:
                raise HTTPException(502, "Proxmox credentials are not configured")
        return self._api

    def _error(self, exc: Exception, *, vmid: int | None = None) -> HTTPException:
        message = str(exc)
        for secret in (self.settings.pve_token_secret, self.settings.pve_password):
            if secret:
                message = message.replace(secret, "[redacted]")
        logger.error("Proxmox request failed vmid=%s node=%s error=%s", vmid, self.settings.pve_node, message)
        return HTTPException(502, f"Не удалось связаться с Proxmox: {message[:500]}")

    def _call(self, operation: Callable[[], Any], *, vmid: int | None = None) -> Any:
        try:
            return operation()
        except (ResourceException, RequestsConnectionError, ConnectionError, TimeoutError, OSError) as exc:
            raise self._error(exc, vmid=vmid) from exc

    def _task_wait(self, upid: str, *, vmid: int | None = None) -> dict:
        deadline = time.monotonic() + self.settings.task_timeout_seconds
        while time.monotonic() < deadline:
            result = self._call(
                lambda: self.api.nodes(self.settings.pve_node).tasks(upid).status.get(), vmid=vmid
            )
            if not result.get("status") or result.get("status") == "stopped":
                if result.get("exitstatus") not in (None, "OK"):
                    raise self._error(RuntimeError(f"task failed: {result.get('exitstatus')}"), vmid=vmid)
                return result
            time.sleep(self.settings.task_poll_interval)
        raise self._error(TimeoutError("Proxmox task timed out"), vmid=vmid)

    def next_free_vmid(self, db: Session | None = None) -> int:
        resources = self._call(lambda: self.api.cluster.resources.get(type="vm"))
        used = {int(item["vmid"]) for item in resources if item.get("vmid") is not None}
        if db is not None:
            used.update(db.scalars(select(VMAssignment.vmid)).all())
        for vmid in range(self.settings.clone_vmid_min, self.settings.clone_vmid_max + 1):
            if vmid not in used:
                return vmid
        raise HTTPException(409, "No free VM IDs in configured range")

    def clone_template(self, new_vmid: int, name: str, template_vmid: int | None = None) -> None:
        source_vmid = template_vmid if template_vmid is not None else self.settings.templates_list()[0].vmid
        params: dict[str, Any] = {"newid": new_vmid, "name": name, "full": int(self.settings.clone_full)}
        if self.settings.clone_full and self.settings.clone_storage:
            params["storage"] = self.settings.clone_storage
        if self.settings.clone_pool:
            params["pool"] = self.settings.clone_pool
        upid = self._call(
            lambda: self.api.nodes(self.settings.pve_node)
            .qemu(source_vmid)
            .clone.post(**params),
            vmid=new_vmid,
        )
        self._task_wait(upid, vmid=new_vmid)

    def _power(self, vmid: int, action: str) -> None:
        upid = self._call(
            lambda: getattr(self.api.nodes(self.settings.pve_node).qemu(vmid).status, action).post(),
            vmid=vmid,
        )
        self._task_wait(upid, vmid=vmid)

    def start(self, vmid: int) -> None:
        self._power(vmid, "start")

    def stop(self, vmid: int) -> None:
        self._power(vmid, "stop")

    def delete(self, vmid: int) -> None:
        try:
            current = self.status(vmid)
            if current.get("status") == "running":
                self.stop(vmid)
        except HTTPException:
            logger.warning("Could not read VM state before deletion vmid=%s", vmid)
        upid = self._call(lambda: self.api.nodes(self.settings.pve_node).qemu(vmid).delete(), vmid=vmid)
        if upid:
            self._task_wait(upid, vmid=vmid)

    def status(self, vmid: int) -> dict:
        return self._call(
            lambda: self.api.nodes(self.settings.pve_node).qemu(vmid).status.current.get(), vmid=vmid
        )

    def vncproxy(self, vmid: int) -> dict:
        return self._call(
            lambda: self.api.nodes(self.settings.pve_node).qemu(vmid).vncproxy.post(
                websocket=1,
                generate_password=1,
            ),
            vmid=vmid,
        )


def get_proxmox_service() -> ProxmoxService:
    return ProxmoxService()
