import asyncio
import contextlib
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis

from app.application.services.chat_service import REDIS_CHANNEL, ChatService
from app.application.uow import UnitOfWork
from app.infrastructure.ai.service import get_ai_service
from app.infrastructure.cache.redis import get_redis
from app.infrastructure.db.repos.sql_repos import SQLConversationRepository
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.security import decode_token
from app.infrastructure.web.middleware.metrics import active_ws_connections
from app.schemas.message import WSError, WSMessageIn

router = APIRouter()

_connected_clients: dict[str, set[WebSocket]] = {}
_WS_IDLE_TIMEOUT = 1800


def _ws_user_id(token: str) -> uuid.UUID | None:
    if not token:
        return None
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None
    return uuid.UUID(payload["sub"])


async def _send_json(ws: WebSocket, data: dict[str, object]) -> None:
    with contextlib.suppress(Exception):
        await ws.send_json(data)


async def _listen_redis(ws: WebSocket, conversation_id: str, redis: Redis) -> None:
    pubsub = redis.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
            except Exception:
                continue
            if data.get("conversation_id") != conversation_id:
                continue
            await _send_json(ws, data)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(REDIS_CHANNEL)
        await pubsub.aclose()  # type: ignore[no-untyped-call]


async def close_all_ws_connections() -> None:
    import structlog
    logger = structlog.get_logger("chat.ws")
    for key, clients in list(_connected_clients.items()):
        for ws in list(clients):
            with contextlib.suppress(Exception):
                await ws.close(code=status.WS_1001_GOING_AWAY, reason="Server shutting down")
        del _connected_clients[key]
    logger.info("all_ws_connections_closed", count=len(_connected_clients))


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(ws: WebSocket, conversation_id: str) -> None:
    token = ws.query_params.get("token", "")
    user_id = _ws_user_id(token)
    if user_id is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing or invalid token")
        return

    conv_id = uuid.UUID(conversation_id)
    factory = get_session_factory()

    async with factory() as session:
        conv_repo = SQLConversationRepository(session)
        conv = await conv_repo.get_by_id(conv_id)
        if conv is None or conv.user_id != user_id:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Conversation not found")
            return

        await ws.accept()

        key = f"{conversation_id}:{user_id}"
        if key not in _connected_clients:
            _connected_clients[key] = set()
        _connected_clients[key].add(ws)
        active_ws_connections.inc()

        redis = await get_redis()
        uow = UnitOfWork(session)
        chat_service = ChatService(uow=uow, ai_service=get_ai_service(), redis=redis)

        redis_task = asyncio.create_task(_listen_redis(ws, conversation_id, redis))

        try:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.receive_text(), timeout=_WS_IDLE_TIMEOUT)
                except TimeoutError:
                    await ws.close(code=status.WS_1001_GOING_AWAY, reason="Idle timeout")
                    break

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await _send_json(ws, WSError(code="invalid_json", message="Invalid JSON").model_dump())
                    continue

                try:
                    msg = WSMessageIn(**data)
                except Exception as e:
                    await _send_json(ws, WSError(code="invalid_message", message=str(e)).model_dump())
                    continue

                await chat_service.handle_user_message(user_id, conv_id, msg.content, msg.client_message_id)
                asyncio.create_task(
                    chat_service.generate_and_broadcast_ai_reply(conv_id, msg.content)
                )
        except WebSocketDisconnect:
            pass
        except Exception as e:
            import structlog
            logger = structlog.get_logger("chat.ws")
            logger.error("ws_error", error=str(e))
        finally:
            redis_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await redis_task
            _connected_clients[key].discard(ws)
            if not _connected_clients[key]:
                del _connected_clients[key]
            active_ws_connections.dec()
