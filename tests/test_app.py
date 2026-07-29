import uuid

import httpx
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from httpx_ws import aconnect_ws
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.infrastructure.db.base import Base
from app.infrastructure.web.main import app

TEST_DB_URL = "postgresql+asyncpg://chat:chatpass@localhost:5433/chatchat_test"


@pytest_asyncio.fixture(autouse=True)
async def setup_and_clean_db():
    test_engine = create_async_engine(TEST_DB_URL)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"TRUNCATE {table.name} CASCADE"))
    await test_engine.dispose()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post("/auth/signup", json={"email": email, "password": "secret123"})
    assert resp.status_code == 201
    data = resp.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}", "_token": token}


@pytest_asyncio.fixture
async def auth_token(auth_headers) -> str:
    return auth_headers["_token"]


class TestAuth:
    async def test_signup(self, client: AsyncClient):
        email = f"new_{uuid.uuid4().hex[:8]}@example.com"
        resp = await client.post("/auth/signup", json={"email": email, "password": "secret123"})
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_signup_duplicate(self, client: AsyncClient):
        email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
        resp = await client.post("/auth/signup", json={"email": email, "password": "secret123"})
        assert resp.status_code == 201
        resp = await client.post("/auth/signup", json={"email": email, "password": "secret123"})
        assert resp.status_code == 409

    async def test_login(self, client: AsyncClient):
        email = f"login_{uuid.uuid4().hex[:8]}@example.com"
        await client.post("/auth/signup", json={"email": email, "password": "secret123"})
        resp = await client.post("/auth/login", json={"email": email, "password": "secret123"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_login_wrong_password(self, client: AsyncClient):
        resp = await client.post("/auth/login", json={"email": "noone@x.com", "password": "wrong"})
        assert resp.status_code == 401

    async def test_refresh(self, client: AsyncClient):
        email = f"ref_{uuid.uuid4().hex[:8]}@example.com"
        signup = await client.post("/auth/signup", json={"email": email, "password": "secret123"})
        refresh_token = signup.json()["refresh_token"]
        resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        assert "access_token" in resp.json()


class TestConversations:
    async def test_create(self, client: AsyncClient, auth_headers):
        resp = await client.post("/conversations", json={"title": "Test Chat"}, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Chat"
        assert "id" in data

    async def test_list(self, client: AsyncClient, auth_headers):
        await client.post("/conversations", json={"title": "Chat 1"}, headers=auth_headers)
        resp = await client.get("/conversations", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1

    async def test_rename(self, client: AsyncClient, auth_headers):
        created = await client.post("/conversations", json={"title": "Old"}, headers=auth_headers)
        cid = created.json()["id"]
        resp = await client.patch(f"/conversations/{cid}", json={"title": "New"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "New"

    async def test_delete(self, client: AsyncClient, auth_headers):
        created = await client.post("/conversations", json={"title": "Delete Me"}, headers=auth_headers)
        cid = created.json()["id"]
        resp = await client.delete(f"/conversations/{cid}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_delete_not_found(self, client: AsyncClient, auth_headers):
        resp = await client.delete(f"/conversations/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404


class TestMessages:
    async def test_send_and_history(self, client: AsyncClient, auth_headers, auth_token):
        conv = await client.post("/conversations", json={"title": "Msg Test"}, headers=auth_headers)
        cid = conv.json()["id"]

        from httpx_ws.transport import ASGIWebSocketTransport
        ws_url = f"http://test/ws/{cid}?token={auth_token}"
        async with (
            httpx.AsyncClient(transport=ASGIWebSocketTransport(app)) as ac,
            aconnect_ws(ws_url, client=ac) as ws,
        ):
            await ws.send_json({"type": "message", "content": "Hello AI"})
            resp = await ws.receive_json()
            assert resp["type"] == "message"
            assert resp["role"] == "user"
            assert resp["content"] == "Hello AI"
            ai_resp = await ws.receive_json()
            assert ai_resp["type"] == "message"
            assert ai_resp["role"] == "assistant"

        hist = await client.get(f"/conversations/{cid}/messages", headers=auth_headers)
        assert hist.status_code == 200
        items = hist.json()["items"]
        assert len(items) >= 2

    async def test_ws_rejects_no_token(self, client: AsyncClient):  # noqa: ARG002
        from httpx_ws.transport import ASGIWebSocketTransport
        async with httpx.AsyncClient(transport=ASGIWebSocketTransport(app)) as ac:
            try:
                async with aconnect_ws("http://test/ws/some-id", client=ac) as ws:
                    await ws.receive_json()
                    raise AssertionError("Expected exception")
            except Exception:
                pass

    async def test_message_pagination(self, client: AsyncClient, auth_headers, auth_token):
        conv = await client.post("/conversations", json={"title": "Paginate"}, headers=auth_headers)
        cid = conv.json()["id"]

        from httpx_ws.transport import ASGIWebSocketTransport
        ws_url = f"http://test/ws/{cid}?token={auth_token}"
        async with (
            httpx.AsyncClient(transport=ASGIWebSocketTransport(app)) as ac,
            aconnect_ws(ws_url, client=ac) as ws,
        ):
            for i in range(5):
                await ws.send_json({"type": "message", "content": f"Msg {i}"})
                await ws.receive_json()
                await ws.receive_json()

        hist = await client.get(f"/conversations/{cid}/messages?limit=2&offset=0", headers=auth_headers)
        assert hist.status_code == 200
        data = hist.json()
        assert len(data["items"]) == 2
        assert data["next_offset"] is not None
        assert data["total"] >= 10

    async def test_pagination_total_count(self, client: AsyncClient, auth_headers, auth_token):
        conv = await client.post("/conversations", json={"title": "Total"}, headers=auth_headers)
        cid = conv.json()["id"]
        from httpx_ws.transport import ASGIWebSocketTransport
        ws_url = f"http://test/ws/{cid}?token={auth_token}"
        async with (
            httpx.AsyncClient(transport=ASGIWebSocketTransport(app)) as ac,
            aconnect_ws(ws_url, client=ac) as ws,
        ):
            for i in range(3):
                await ws.send_json({"type": "message", "content": f"N{i}"})
                await ws.receive_json()
                await ws.receive_json()
        hist = await client.get(f"/conversations/{cid}/messages?limit=10&offset=0", headers=auth_headers)
        assert hist.status_code == 200
        data = hist.json()
        assert data["total"] == 6

    async def test_ws_rejects_bad_token(self, client: AsyncClient):  # noqa: ARG002
        from httpx_ws.transport import ASGIWebSocketTransport
        async with httpx.AsyncClient(transport=ASGIWebSocketTransport(app)) as ac:
            try:
                async with aconnect_ws("http://test/ws/some-id?token=invalidtoken", client=ac) as ws:
                    await ws.receive_json()
                    raise AssertionError("Expected exception")
            except Exception:
                pass

    async def test_ws_rejects_wrong_conversation(self, client: AsyncClient, auth_token):  # noqa: ARG002
        from httpx_ws.transport import ASGIWebSocketTransport
        async with httpx.AsyncClient(transport=ASGIWebSocketTransport(app)) as ac:
            try:
                async with aconnect_ws(f"http://test/ws/{uuid.uuid4()}?token={auth_token}", client=ac) as ws:
                    await ws.receive_json()
                    raise AssertionError("Expected exception")
            except Exception:
                pass


class TestCrossInstanceFanOut:
    async def test_redis_pub_sub_works(self):
        from app.infrastructure.cache.redis import get_redis
        redis = await get_redis()
        ch = "test:channel"
        pubsub = redis.pubsub()
        await pubsub.subscribe(ch)
        await pubsub.get_message(timeout=2)
        await redis.publish(ch, "hello")
        msg = await pubsub.get_message(timeout=2)
        assert msg is not None
        assert msg["type"] == "message"
        assert msg["data"] == "hello"
        await pubsub.unsubscribe(ch)
        await pubsub.aclose()
