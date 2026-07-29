import uuid

from app.application.uow import UnitOfWork
from app.infrastructure.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.schemas.auth import TokenResponse, UserResponse


class AuthService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def signup(self, email: str, password: str) -> TokenResponse:
        existing = await self._uow.users.get_by_email(email)
        if existing:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        user = await self._uow.users.create(email, hash_password(password))
        await self._uow.commit()
        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self._uow.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        from app.infrastructure.security import decode_token
        payload = decode_token(refresh_token)
        if payload is None or payload.get("type") != "refresh":
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
        user_id = uuid.UUID(payload["sub"])
        return TokenResponse(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )

    async def get_profile(self, user_id: uuid.UUID) -> UserResponse:
        user = await self._uow.users.get_by_id(user_id)
        if user is None:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return UserResponse.model_validate(user)
