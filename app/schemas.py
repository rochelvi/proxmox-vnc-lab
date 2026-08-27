from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool
    created_at: datetime
    can_change_password: bool = True

    model_config = ConfigDict(from_attributes=True)


class VMAssignmentResponse(BaseModel):
    id: int
    user_id: int
    vmid: int
    node: str
    name: str
    template_vmid: int | None
    template_label: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VMAssignmentRequest(BaseModel):
    template_vmid: int | None = None


class TemplateResponse(BaseModel):
    vmid: int
    label: str


class VNCResponse(BaseModel):
    ticket: str
    port: int
    ws_path: str
    password: str
