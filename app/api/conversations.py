import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import get_current_user_id
from app.core.ai import get_ai_service
from app.core.uow import UnitOfWork
from app.db.session import get_uow
from app.schemas.conversation import (
    ConversationCreate,
    ConversationList,
    ConversationResponse,
    ConversationUpdate,
)
from app.schemas.message import MessageHistory, MessageResponse
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _conversation_service(uow: UnitOfWork = Depends(get_uow)) -> ConversationService:
    return ConversationService(uow)


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create(
    body: ConversationCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    svc: ConversationService = Depends(_conversation_service),
):
    return await svc.create(user_id, body.title)


@router.get("", response_model=ConversationList)
async def list_conversations(
    user_id: uuid.UUID = Depends(get_current_user_id),
    svc: ConversationService = Depends(_conversation_service),
):
    return await svc.list_for_user(user_id)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    svc: ConversationService = Depends(_conversation_service),
):
    return await svc.rename(user_id, conversation_id, body.title)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    svc: ConversationService = Depends(_conversation_service),
):
    await svc.delete(user_id, conversation_id)


async def _chat_history_service(uow: UnitOfWork = Depends(get_uow)) -> ChatService:
    from app.core.redis import get_redis
    redis = await get_redis()
    return ChatService(uow=uow, ai_service=get_ai_service(), redis=redis)


@router.get("/{conversation_id}/messages", response_model=MessageHistory)
async def history(
    conversation_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: uuid.UUID = Depends(get_current_user_id),
    chat_svc: ChatService = Depends(_chat_history_service),
):
    if not await chat_svc.verify_conversation_access(user_id, conversation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    messages, total, has_more = await chat_svc.get_history(conversation_id, limit, offset)
    return MessageHistory(
        items=[MessageResponse.model_validate(m) for m in messages],
        total=total,
        next_offset=offset + limit if has_more else None,
    )
