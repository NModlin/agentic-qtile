#!/usr/bin/env python3
"""
Agent Bridge Demo Script

Connects to the AgentBridge socket and exercises the JSON-RPC API.
Run this while Qtile with Agentic patches is running.

Usage:
    python3 scripts/agent_demo.py
"""
import asyncio
import json
import os
import sys

SOCKET_PATH = os.path.expanduser("~/.cache/qtile/agent_bridge.socket")


async def send_rpc(method: str, params=None, msg_id: int = 1):
    """Send a JSON-RPC 2.0 request and return the response."""
    request = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": msg_id}
    payload = json.dumps(request).encode()

    try:
        reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)
    except (FileNotFoundError, ConnectionRefusedError):
        print(f"❌ Cannot connect to {SOCKET_PATH}")
        print("   Make sure Qtile with Agentic patches is running.")
        sys.exit(1)

    writer.write(payload)
    writer.write_eof()

    data = await reader.read()
    writer.close()
    await writer.wait_closed()

    return json.loads(data.decode())


async def main():
    print("🤖 Agentic Qtile – Agent Bridge Demo")
    print("=" * 50)

    # 1. Echo test
    print("\n📡 1. Echo test...")
    resp = await send_rpc("echo", "hello from agent!", 1)
    print(f"   Response: {json.dumps(resp, indent=2)}")

    # 2. Get windows
    print("\n🪟  2. Get all windows...")
    resp = await send_rpc("get_windows", {}, 2)
    windows = resp.get("result", [])
    print(f"   Found {len(windows)} windows:")
    for w in windows[:5]:
        print(f"   - [{w['id']}] {w['name']}")
    if len(windows) > 5:
        print(f"   ... and {len(windows) - 5} more")

    # 3. Get groups
    print("\n📂 3. Get groups...")
    resp = await send_rpc("get_groups", {}, 3)
    groups = resp.get("result", [])
    for g in groups:
        print(f"   - {g['name']} (layout: {g.get('layout')}, windows: {len(g.get('windows', []))})")

    # 4. Get focused window
    print("\n🎯 4. Get focused window...")
    resp = await send_rpc("get_focused", {}, 4)
    focused = resp.get("result")
    if focused:
        print(f"   Focused: [{focused['id']}] {focused['name']}")

        # 5. Set agent metadata on focused window
        print("\n🏷️  5. Setting agent metadata on focused window...")
        metadata = {
            "agent_id": "demo-agent-1",
            "confidence": 0.87,
            "status": "active",
            "task": "demo-exploration",
        }
        resp = await send_rpc("set_agent_metadata", {
            "window_id": focused["id"],
            "metadata": metadata,
        }, 5)
        print(f"   Result: {resp.get('result')}")

        # 6. Read it back
        print("\n📖 6. Reading agent metadata back...")
        resp = await send_rpc("get_agent_metadata", {"window_id": focused["id"]}, 6)
        print(f"   Metadata: {json.dumps(resp.get('result'), indent=2)}")

        # 7. Ralph Wiggin: mark as pending
        print("\n🛑 7. Ralph Wiggin: marking window as pending verification...")
        resp = await send_rpc("verify_completion", {
            "window_id": focused["id"],
            "complete": False,
        }, 7)
        print(f"   Result: {resp.get('result')}")

        # 8. Ralph Wiggin: mark as complete
        print("\n✅ 8. Ralph Wiggin: marking window as complete...")
        resp = await send_rpc("verify_completion", {
            "window_id": focused["id"],
            "complete": True,
        }, 8)
        print(f"   Result: {resp.get('result')}")
    else:
        print("   No focused window")

    # 9. Try slot operations (only works with GenerativeLayout)
    print("\n🔲 9. Creating semantic slot (requires GenerativeLayout)...")
    resp = await send_rpc("create_slot", {
        "name": "agent-workspace",
        "x": 0.7, "y": 0.0,
        "w": 0.3, "h": 1.0,
    }, 9)
    if "error" in resp:
        print(f"   ⚠️  {resp['error'].get('message', 'Error')} (expected if not using GenerativeLayout)")
    else:
        print(f"   Created: {json.dumps(resp.get('result'), indent=2)}")

        # List slots
        resp = await send_rpc("list_slots", {}, 10)
        print(f"   All slots: {json.dumps(resp.get('result'), indent=2)}")

        # Clean up
        await send_rpc("remove_slot", {"name": "agent-workspace"}, 11)
        print("   Cleaned up slot.")

    print("\n" + "=" * 50)
    print("✨ Demo complete! Check ~/.cache/qtile/agent_events.jsonl for event log.")


if __name__ == "__main__":
    asyncio.run(main())
