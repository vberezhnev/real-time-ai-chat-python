from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repos.sql_repos import (
    SQLConversationRepository,
    SQLMessageRepository,
    SQLUserRepository,
)


class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.users = SQLUserRepository(session)
        self.conversations = SQLConversationRepository(session)
        self.messages = SQLMessageRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    @property
    def session(self) -> AsyncSession:
        return self._session
