from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth_providers import get_auth_provider
from app.config import get_settings
from app.db import get_db
from app.schemas import LoginRequest, TokenResponse, UserResponse
from app.security import create_access_token, get_current_user

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
    return UserResponse.model_validate(user)
