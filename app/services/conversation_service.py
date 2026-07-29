import uuid

from app.core.uow import UnitOfWork
from app.models.conversation import Conversation
from app.schemas.conversation import ConversationList, ConversationResponse


class ConversationService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def create(self, user_id: uuid.UUID, title: str) -> ConversationResponse:
        conv = await self._uow.conversations.create(user_id, title)
        await self._uow.commit()
        return ConversationResponse.model_validate(conv)

    async def list_for_user(self, user_id: uuid.UUID) -> ConversationList:
        items = await self._uow.conversations.list_by_user(user_id)
        return ConversationList(items=[ConversationResponse.model_validate(c) for c in items])

    async def _get_owned_or_404(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
        from fastapi import HTTPException, status
        conv = await self._uow.conversations.get_by_id(conversation_id)
        if conv is None or conv.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return conv

    async def rename(self, user_id: uuid.UUID, conversation_id: uuid.UUID, title: str) -> ConversationResponse:
        await self._get_owned_or_404(user_id, conversation_id)
        conv = await self._uow.conversations.update_title(conversation_id, title)
        await self._uow.commit()
        return ConversationResponse.model_validate(conv)

    async def delete(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        from fastapi import HTTPException, status
        conv = await self._uow.conversations.get_by_id(conversation_id)
        if conv is None or conv.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        await self._uow.conversations.soft_delete(conversation_id)
        await self._uow.commit()
