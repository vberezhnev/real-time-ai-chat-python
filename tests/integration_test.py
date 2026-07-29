"""
Integration test — runs against the actual server at localhost:8000.
Assumes DB + Redis are up and running.
"""

import asyncio
import json
import sys
import uuid

import httpx
import websockets

WS_BASE = "ws://localhost:8000"
REST_BASE = "http://localhost:8000"

passed = 0
failed = 0


async def check(name: str, coro):
    global passed, failed
    try:
        resp = await coro
        print(f"  [{resp.status_code}] {name}")
        return resp
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        failed += 1
        return None


async def main():
    global passed, failed
    async with httpx.AsyncClient(base_url=REST_BASE, timeout=10) as c:
        email = f"inttest_{uuid.uuid4().hex[:8]}@example.com"
        pw = "secret123"

        # 1. Health
        r = await check("health", c.get("/health"))
        if r: passed += 1

        # 2. Signup
        r = await check("signup", c.post("/auth/signup", json={"email": email, "password": pw}))
        if r:
            passed += 1
            data = r.json()
            access = data["access_token"]
            refresh = data["refresh_token"]
        else:
            print("  ABORT: signup failed")
            return

        # 3. Duplicate signup -> 409
        r = await check("signup duplicate", c.post("/auth/signup", json={"email": email, "password": pw}))
        if r and r.status_code == 409:
            passed += 1
        else:
            failed += 1

        # 4. Login
        r = await check("login", c.post("/auth/login", json={"email": email, "password": pw}))
        if r and "access_token" in r.text:
            passed += 1
        else:
            failed += 1

        # 5. Login wrong password -> 401
        r = await check("login wrong pw", c.post("/auth/login", json={"email": email, "password": "wrong"}))
        if r and r.status_code == 401:
            passed += 1
        else:
            failed += 1

        # 6. Me
        r = await check("me", c.get("/auth/me", headers={"Authorization": f"Bearer {access}"}))
        if r and r.json()["email"] == email:
            passed += 1
        else:
            failed += 1

        # 7. Me without token -> 401
        r = await check("me no token", c.get("/auth/me"))
        if r and r.status_code == 401:
            passed += 1
        else:
            failed += 1

        # 8. Refresh
        r = await check("refresh", c.post("/auth/refresh", json={"refresh_token": refresh}))
        if r and "access_token" in r.text:
            passed += 1
            access = r.json()["access_token"]
        else:
            failed += 1

        # 9. Create conversation
        r = await check("create conv", c.post("/conversations",
                                                json={"title": "Int Test"},
                                                headers={"Authorization": f"Bearer {access}"}))
        if r:
            passed += 1
            conv_id = r.json()["id"]
        else:
            print("  ABORT: create conv failed")
            return

        # 10. List conversations
        r = await check("list convs", c.get("/conversations",
                                              headers={"Authorization": f"Bearer {access}"}))
        if r and len(r.json()["items"]) == 1:
            passed += 1
        else:
            failed += 1

        # 11. Rename
        r = await check("rename", c.patch(f"/conversations/{conv_id}",
                                           json={"title": "Renamed"},
                                           headers={"Authorization": f"Bearer {access}"}))
        if r and r.json()["title"] == "Renamed":
            passed += 1
        else:
            failed += 1

        # 12. Message history (empty)
        r = await check("messages empty", c.get(f"/conversations/{conv_id}/messages",
                                                  headers={"Authorization": f"Bearer {access}"}))
        if r and r.json()["items"] == []:
            passed += 1
        else:
            failed += 1

        # 13. Delete
        r = await check("delete conv", c.delete(f"/conversations/{conv_id}",
                                                  headers={"Authorization": f"Bearer {access}"}))
        if r and r.status_code == 204:
            passed += 1
        else:
            failed += 1

        # 14. List after delete (empty)
        r = await check("list after delete", c.get("/conversations",
                                                     headers={"Authorization": f"Bearer {access}"}))
        if r and len(r.json()["items"]) == 0:
            passed += 1
        else:
            failed += 1

        # 15. Access isolation (user2 sees empty list)
        email2 = f"inttest_{uuid.uuid4().hex[:8]}@example.com"
        r2 = await check("signup user2", c.post("/auth/signup", json={"email": email2, "password": pw}))
        if r2:
            access2 = r2.json()["access_token"]
            r = await check("user2 list", c.get("/conversations",
                                                  headers={"Authorization": f"Bearer {access2}"}))
            if r and len(r.json()["items"]) == 0:
                passed += 1
            else:
                failed += 1
        else:
            failed += 1

        # 16. WebSocket: create a new conversation and send a message
        r = await check("create conv2", c.post("/conversations",
                                                 json={"title": "WS Test"},
                                                 headers={"Authorization": f"Bearer {access}"}))
        if r:
            passed += 1
            ws_conv_id = r.json()["id"]
        else:
            failed += 1
            ws_conv_id = None

        if ws_conv_id:
            try:
                ws_url = f"{WS_BASE}/ws/{ws_conv_id}?token={access}"
                async with websockets.connect(ws_url) as ws:
                    await ws.send(json.dumps({"type": "message", "content": "hello"}))
                    # We expect the user message echoed back, then AI reply
                    msg1 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    msg2 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    print(f"  [WS] user  msg: {msg1['content'][:30]}")
                    print(f"  [WS] ai    msg: {msg2['content'][:30]}")
                    if msg1["role"] == "user" and msg2["role"] == "assistant":
                        passed += 1
                    else:
                        failed += 1
            except Exception as e:
                print(f"  [FAIL] ws: {e}")
                failed += 1

        # 17. Verify messages persisted via REST
        r = await check("messages after WS", c.get(f"/conversations/{ws_conv_id}/messages",
                                                      headers={"Authorization": f"Bearer {access}"}))
        if r and len(r.json()["items"]) == 2:
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*40}")
    print(f"  Passed: {passed} / {passed + failed}")
    print(f"  Failed: {failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
