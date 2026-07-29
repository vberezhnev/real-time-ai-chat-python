import uuid

from typing import Protocol

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User


class UserRepository(Protocol):
    async def create(self, email: str, password_hash: str) -> User: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...


class ConversationRepository(Protocol):
    async def create(self, user_id: uuid.UUID, title: str) -> Conversation: ...
    async def list_by_user(self, user_id: uuid.UUID) -> list[Conversation]: ...
    async def get_by_id(self, conversation_id: uuid.UUID) -> Conversation | None: ...
    async def update_title(self, conversation_id: uuid.UUID, title: str) -> Conversation | None: ...
    async def soft_delete(self, conversation_id: uuid.UUID) -> bool: ...


class MessageRepository(Protocol):
    async def create(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        sender_id: uuid.UUID | None = None,
        client_message_id: str | None = None,
    ) -> Message: ...

    async def list_by_conversation(
        self,
        conversation_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Message], int]: ...


class AIService(Protocol):
    async def generate_reply(self, user_message: str) -> str: ...
