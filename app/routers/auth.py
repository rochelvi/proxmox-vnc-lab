from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth_providers import get_auth_provider
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, PasswordChangeRequest, TokenResponse, UserResponse
from app.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = LoginRequest.model_validate(await request.json())
    else:
        form = await request.form()
        payload = LoginRequest(username=str(form.get("username", "")), password=str(form.get("password", "")))
    try:
        provider = get_auth_provider(get_settings().auth_provider, db)
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    user = provider.authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(401, "Invalid username or password")
    return TokenResponse(access_token=create_access_token(user))


@router.get("/me", response_model=UserResponse)
def me(user=Depends(get_current_user)) -> UserResponse:
    local_auth = get_settings().auth_provider.lower() == "local"
    return UserResponse.model_validate(user).model_copy(
        update={"can_change_password": local_auth and bool(user.password_hash)}
    )


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    if get_settings().auth_provider.lower() != "local":
        raise HTTPException(400, "Смена пароля доступна только при локальной аутентификации")
    if not user.password_hash or not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Текущий пароль указан неверно")
    if payload.current_password == payload.new_password:
        raise HTTPException(400, "Новый пароль должен отличаться от текущего")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
