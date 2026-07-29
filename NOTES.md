# Notes

## Structure

```
app/
  main.py            — FastAPI app, lifespan, CORS, exception handler
  config.py          — pydantic-settings
  api/
    auth.py          — signup/login/refresh/me (REST)
    conversations.py — CRUD + history (REST)
    ws.py            — WebSocket endpoint, Redis pub/sub listener, mock AI
  core/
    security.py      — JWT encode/decode, bcrypt hash/verify
    redis.py         — lazy Redis client singleton
  db/
    base.py          — SQLAlchemy DeclarativeBase
    session.py       — lazy engine + session factory
    repositories.py  — all DB queries as plain async functions
  models/            — User, Conversation, Message (SQLAlchemy)
  schemas/           — Pydantic v2 models for request/response
```

## Key Decisions

### WebSocket Auth: Query Param

Chose `?token=` query param over subprotocol or first-message auth because:
- **Subprotocol** — cleaner but needs client support and adds complexity to the first message dance.
- **First-message auth** — adds latency (must wait for first frame) and state management (unauthenticated -> authenticated state transition).
- **Query param** — simplest; the token is available at handshake time, rejected immediately with a close code before `accept()`. Trade-off: token appears in server logs. Acceptable for a backend test.

### REST vs WebSocket split

- **Auth + CRUD** — REST. Stateless, cacheable, standard tooling.
- **Messaging** — WebSocket. Live push, bidirectional, low-latency.

### SQLAlchemy + asyncpg

SQLAlchemy 2.0 async with `asyncpg`. Chose over raw asyncpg for:
- Declarative models + Alembic migrations (reproducible schema).
- Repository pattern keeps queries simple while allowing reuse.

### Redis pub/sub for fan-out

Messages published to `chat:messages` channel. Each WS client runs a background `asyncio.Task` listening on that channel, filtering by `conversation_id`. This allows 2+ app replicas to exchange messages.

## What's Cut

- **Soft-delete restore** — `is_deleted` flag exists but no restore endpoint. Easy to add.
- **Cursor-based pagination** — offset pagination works for expected scale. Cursor would be more robust for large histories.
- **Typing indicators / presence** — would add complexity to client tracking. Not needed for core.
- **Rate limiting** — not required at this scope.
- **Streamed assistant reply** — mock AI returns full reply. Streaming token-by-token is straightforward with Redis pub/sub but adds complexity to the WS protocol.

## Self-Critique

1. **Engine lifecycle** — Lazy engine creation (singleton pattern) works but the global module state makes testing harder. Better: dependency injection with a registry.
2. **No explicit connection pool tuning** — defaults are fine for a test but need tuning for production.
3. **Redis client singleton** — same pattern as DB engine. Works but less testable.
4. **No rate limiting** — a real service needs per-user Redis-based rate limiting on WS messages.
5. **Soft-delete** — `is_deleted` column exists but delete is permanent in API. Restore endpoint trivial to add.
6. **Logging** — structured `logging` only. In production, use `structlog` or `loguru` with JSON output.
7. **No health check for dependencies** — `/health` should check Postgres and Redis connectivity.
8. **CORS** — allow all origins (`*`). Production needs explicit origins.
