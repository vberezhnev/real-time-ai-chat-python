import asyncio

from app.domain.ports import AIService


class MockAIService:
    async def generate_reply(self, user_message: str) -> str:
        await asyncio.sleep(0.5)
        return f"You said: {user_message}"


_ai_instance: AIService | None = None


def get_ai_service() -> AIService:
    global _ai_instance
    if _ai_instance is None:
        _ai_instance = MockAIService()
    return _ai_instance
