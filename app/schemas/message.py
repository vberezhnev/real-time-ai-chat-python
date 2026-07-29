import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID | None
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageHistory(BaseModel):
    items: list[MessageResponse]
    total: int
    next_offset: int | None = None


class WSMessageIn(BaseModel):
    type: str = "message"
    content: str
    client_message_id: str | None = None


class WSMessageOut(BaseModel):
    type: str
    content: str
    role: str
    sender_id: str | None
    message_id: str
    client_message_id: str | None = None
    conversation_id: str
    timestamp: str


class WSError(BaseModel):
    type: str = "error"
    code: str
    message: str
