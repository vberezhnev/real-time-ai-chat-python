# Real-Time AI Chat Backend

## Stack

FastAPI · Python 3.12+ · WebSockets · PostgreSQL · Redis (pub/sub) · SQLAlchemy (async) · Alembic

## Quick Start

```bash
docker compose up -d
# Migrations run automatically on app start
```

This starts API on `:8000`, PostgreSQL on `:5433`, Redis on `:6380`.

### Manual migration (if needed)

```bash
alembic upgrade head
```

## Test

```bash
PYTHONPATH=. pytest tests/ -v
```

Requires `chatchat_test` DB (created automatically by `docker compose`).

## Demo (websocat)

```bash
# 1. Sign up
SIGNUP=$(curl -s -X POST http://localhost:8000/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@test.com","password":"pass123"}')
TOKEN=$(echo $SIGNUP | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
echo "Token: $TOKEN"

# 2. Create conversation
CONV=$(curl -s -X POST http://localhost:8000/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Demo Chat"}')
CID=$(echo $CONV | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "Conversation: $CID"

# 3. WebSocket — send message, see broadcast + AI reply
websocat "ws://localhost:8000/ws/$CID?token=$TOKEN"
# type: {"type":"message","content":"Hello!"}

# 4. Fetch message history
curl -s "http://localhost:8000/conversations/$CID/messages" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

## What's Built

- **Auth** — signup/login with JWT (access + refresh tokens), bcrypt hashing
- **Conversations CRUD** — create, list, rename, soft-delete
- **Real-time messaging** — WebSocket send/broadcast with Redis pub/sub fan-out
- **Mock AI** — echo reply ("You said: {msg}") with simulated delay
- **History** — paginated message fetch (offset-based)
- **Tests** — 14 tests covering auth, CRUD, WS send/persist/broadcast, Redis fan-out

## Protocol

WebSocket auth via query param `?token=`. JSON messages with `type`, `content`, `role`, `message_id`, `conversation_id`, `timestamp`.
