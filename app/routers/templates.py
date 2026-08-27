from fastapi import APIRouter, Depends

from app.config import get_settings
from app.schemas import TemplateResponse
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["templates"])


@router.get("/templates", response_model=list[TemplateResponse])
def list_templates(user=Depends(get_current_user)) -> list[TemplateResponse]:
    del user
    return [TemplateResponse(vmid=template.vmid, label=template.label) for template in get_settings().templates_list()]
