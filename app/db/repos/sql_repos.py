import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User


class SQLUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class SQLConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: uuid.UUID, title: str) -> Conversation:
        conv = Conversation(title=title, user_id=user_id)
        self._session.add(conv)
        await self._session.flush()
        await self._session.refresh(conv)
        return conv

    async def list_by_user(self, user_id: uuid.UUID) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.is_deleted.is_(False))
            .order_by(Conversation.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.is_deleted.is_(False))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_title(self, conversation_id: uuid.UUID, title: str) -> Conversation | None:
        conv = await self.get_by_id(conversation_id)
        if conv is None:
            return None
        conv.title = title
        conv.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        await self._session.refresh(conv)
        return conv

    async def soft_delete(self, conversation_id: uuid.UUID) -> bool:
        conv = await self.get_by_id(conversation_id)
        if conv is None:
            return False
        conv.is_deleted = True
        conv.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return True


class SQLMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        sender_id: uuid.UUID | None = None,
        client_message_id: str | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sender_id=sender_id,
            client_message_id=client_message_id,
        )
        self._session.add(msg)
        await self._session.flush()
        await self._session.refresh(msg)
        return msg

    async def list_by_conversation(
        self,
        conversation_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Message], int]:
        count_stmt = select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        result = await self._session.execute(stmt)
        messages = list(result.scalars().all())
        return messages, total
