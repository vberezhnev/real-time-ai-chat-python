import asyncio
import uuid
from typing import Any

from redis.asyncio import Redis

from app.application.uow import UnitOfWork
from app.domain.ports import AIService
from app.schemas.message import WSMessageOut


class MockAIService:
    async def generate_reply(self, user_message: str) -> str:
        await asyncio.sleep(0.5)
        return f"You said: {user_message}"


REDIS_CHANNEL = "chat:messages"


class ChatService:
    def __init__(
        self,
        uow: UnitOfWork,
        ai_service: AIService,
        redis: Redis,
    ) -> None:
        self._uow = uow
        self._ai_service = ai_service
        self._redis = redis

    async def handle_user_message(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        content: str,
        client_message_id: str | None = None,
    ) -> WSMessageOut:
        msg = await self._uow.messages.create(
            conversation_id=conversation_id,
            role="user",
            content=content,
            sender_id=user_id,
            client_message_id=client_message_id,
        )
        out = WSMessageOut(
            type="message",
            content=msg.content,
            role="user",
            sender_id=str(user_id),
            message_id=str(msg.id),
            client_message_id=client_message_id,
            conversation_id=str(conversation_id),
            timestamp=msg.created_at.isoformat(),
        )
        await self._redis.publish(REDIS_CHANNEL, out.model_dump_json())
        await self._uow.commit()
        return out

    async def generate_and_broadcast_ai_reply(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
    ) -> None:
        from app.application.uow import UnitOfWork as UoW
        from app.infrastructure.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            uow = UoW(session)
            reply_text = await self._ai_service.generate_reply(user_message)
            msg = await uow.messages.create(
                conversation_id=conversation_id,
                role="assistant",
                content=reply_text,
            )
            out = WSMessageOut(
                type="message",
                content=msg.content,
                role="assistant",
                sender_id=None,
                message_id=str(msg.id),
                conversation_id=str(conversation_id),
                timestamp=msg.created_at.isoformat(),
            )
            await self._redis.publish(REDIS_CHANNEL, out.model_dump_json())
            await uow.commit()

    async def get_history(self, conversation_id: uuid.UUID, limit: int, offset: int) -> tuple[list[Any], int, bool]:
        messages, total = await self._uow.messages.list_by_conversation(conversation_id, limit, offset)
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]
        return messages, total, has_more

    async def verify_conversation_access(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        conv = await self._uow.conversations.get_by_id(conversation_id)
        return conv is not None and conv.user_id == user_id
