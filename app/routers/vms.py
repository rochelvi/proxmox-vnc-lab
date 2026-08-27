import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User, VMAssignment
from app.proxmox import ProxmoxService, get_proxmox_service
from app.schemas import VMAssignmentResponse, VNCResponse
from app.security import get_current_user

router = APIRouter(prefix="/api/vms", tags=["vms"])
allocation_lock = threading.Lock()
logger = logging.getLogger(__name__)


def _assignment_or_404(vmid: int, user: User, db: Session) -> VMAssignment:
    assignment = db.scalar(select(VMAssignment).where(VMAssignment.vmid == vmid))
    if assignment is None:
        raise HTTPException(404, "VM assignment not found")
    if assignment.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "You do not own this VM")
    return assignment


@router.post("", response_model=VMAssignmentResponse, status_code=status.HTTP_201_CREATED)
def assign_vm(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    pve: ProxmoxService = Depends(get_proxmox_service),
) -> VMAssignment:
    settings = get_settings()
    with allocation_lock:
        count = len(db.scalars(select(VMAssignment).where(VMAssignment.user_id == user.id)).all())
        if count >= settings.max_vms_per_user:
            raise HTTPException(409, "VM limit reached")
        vmid = pve.next_free_vmid(db)
        name = f"{settings.clone_name_prefix}-{user.username}-{vmid}"
        assignment = VMAssignment(
            user_id=user.id, vmid=vmid, node=settings.pve_node, name=name, status="creating"
        )
        db.add(assignment)
        db.flush()
        try:
            pve.clone_template(vmid, name)
            pve.start(vmid)
            assignment.status = "running"
            db.commit()
            db.refresh(assignment)
            return assignment
        except Exception:
            db.rollback()
            try:
                pve.delete(vmid)
            except Exception:
                logger.warning("Best-effort cleanup failed vmid=%s", vmid, exc_info=True)
            raise


@router.get("", response_model=list[VMAssignmentResponse])
def list_vms(
    all: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    pve: ProxmoxService = Depends(get_proxmox_service),
) -> list[VMAssignment]:
    query = select(VMAssignment)
    if not (all and user.is_admin):
        query = query.where(VMAssignment.user_id == user.id)
    assignments = list(db.scalars(query).all())
    for assignment in assignments:
        try:
            live = pve.status(assignment.vmid)
            assignment.status = str(live.get("status", assignment.status))
        except HTTPException:
            pass
    return assignments


@router.post("/{vmid}/stop", response_model=VMAssignmentResponse)
def stop_vm(
    vmid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    pve: ProxmoxService = Depends(get_proxmox_service),
) -> VMAssignment:
    assignment = _assignment_or_404(vmid, user, db)
    pve.stop(vmid)
    assignment.status = "stopped"
    db.commit()
    db.refresh(assignment)
    return assignment


@router.post("/{vmid}/start", response_model=VMAssignmentResponse)
def start_vm(
    vmid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    pve: ProxmoxService = Depends(get_proxmox_service),
) -> VMAssignment:
    assignment = _assignment_or_404(vmid, user, db)
    pve.start(vmid)
    assignment.status = "running"
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{vmid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vm(
    vmid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    pve: ProxmoxService = Depends(get_proxmox_service),
) -> None:
    assignment = _assignment_or_404(vmid, user, db)
    pve.delete(vmid)
    db.delete(assignment)
    db.commit()


@router.get("/{vmid}/vnc", response_model=VNCResponse)
def vnc(
    vmid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    pve: ProxmoxService = Depends(get_proxmox_service),
) -> VNCResponse:
    _assignment_or_404(vmid, user, db)
    result = pve.vncproxy(vmid)
    ticket = str(result["ticket"])
    return VNCResponse(
        ticket=ticket,
        port=int(result["port"]),
        ws_path=f"/api/vms/{vmid}/ws",
        password=ticket,
    )
