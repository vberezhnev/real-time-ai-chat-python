import asyncio

from app.config import settings
from app.core.interfaces import AIService


class MockAIService:
    async def generate_reply(self, user_message: str) -> str:
        await asyncio.sleep(0.5)
        return f"You said: {user_message}"


_ai_instance: AIService | None = None


def get_ai_service() -> AIService:
    global _ai_instance
    if _ai_instance is None:
        provider = settings.ai_provider
        if provider == "mock":
            _ai_instance = MockAIService()
        else:
            _ai_instance = MockAIService()
    return _ai_instance
