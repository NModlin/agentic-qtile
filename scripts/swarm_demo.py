
import asyncio
import json
import os
import sys
import struct

# Constants
SOCK_PATH = os.path.expanduser("~/.cache/qtile/agent_bridge.socket")

async def rpc_call(method, params=None):
    """Send JSON-RPC request and return result (with msgpack support)."""
    if params is None:
        params = {}
    
    try:
        reader, writer = await asyncio.open_unix_connection(SOCK_PATH)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

    req = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
    }
    
    try:
        msg = json.dumps(req).encode()
        writer.write(msg)
        writer.write_eof()
        await writer.drain()
        
        data = await reader.read()
    except Exception as e:
        print(f"❌ IO Error: {e}")
        return None
    finally:
        writer.close()
        try:
           await writer.wait_closed()
        except:
           pass
        
    if not data:
        return None
        
    try:
        resp = json.loads(data.decode())
    except json.JSONDecodeError:
        print(f"❌ Failed to decode response: {data}")
        return None

    if "error" in resp:
        print(f"❌ RPC Error: {resp['error']}")
        return None
        
    return resp.get("result")

async def agent_lifecycle(name, color, delay, proposals):
    """Simulate an independent agent."""
    print(f"🤖 Agent '{name}' is coming online (Delay: {delay}s)...")
    await asyncio.sleep(delay)
    
    for prop in proposals:
        prop["owner"] = name
        print(f"⚡ {name} proposing: {prop['name']} at x={prop['x']}")
        res = await rpc_call("propose_slot", prop)
        print(f"   Result: {res}")
        await asyncio.sleep(0.5)

async def main():
    if not os.path.exists(SOCK_PATH):
        print(f"❌ Socket not found at {SOCK_PATH}")
        sys.exit(1)

    print("🐝 Starting Multi-Agent Swarm Simulation...")
    
    # Clear slate
    await rpc_call("clear_ghost_slots")
    
    # Define Agents strategies
    # Agent A wants the Left Half
    strategy_a = [
        {"name": "Browser", "x": 0.0, "y": 0.0, "w": 0.5, "h": 1.0}
    ]
    
    # Agent B wants the Center (overlaps with A)
    strategy_b = [
        {"name": "IDE", "x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5}
    ]
    
    # Run them concurrently
    await asyncio.gather(
        agent_lifecycle("Alpha", "blue", 0.0, strategy_a),
        agent_lifecycle("Beta", "green", 1.0, strategy_b)
    )
    
    print("\n⚠️  Conflict should now be visible (RED borders).")
    
    # VERIFICATION: Check Layout Info
    layout_info = await rpc_call("get_layout")
    print(f"DEBUG: layout_info keys: {layout_info.keys()}")
    ghosts = layout_info.get("ghost_slots", [])
    print(f"DEBUG: Found {len(ghosts)} ghosts: {[g.get('name') for g in ghosts]}")
    for g in ghosts:
        print(f"   Ghost {g.get('name')}: conflict={g.get('conflict')}")

    conflict_count = sum(1 for g in ghosts if g.get("conflict"))
    print(f"🔍 Inspector detected {conflict_count} conflicting ghost slots.")
    
    if conflict_count == 2:
        print("✅ SUCCESS: Conflict detection working! Both slots flagged.")
    else:
        print(f"❌ FAILURE: Expected 2 conflicts, found {conflict_count}.")

    input("Press Enter to resolve conflict (Agent A yields)...")
    
    # Resolution: Remove A's proposal?
    # We can't "remove" a single ghost slot easily via RPC yet (only clear all).
    # But we can re-propose B?
    # Actually, let's clear and just let B win.
    print("🏳️  Alpha yields.")
    await rpc_call("clear_ghost_slots")
    
    for prop in strategy_b:
        prop["owner"] = "Beta"
        await rpc_call("propose_slot", prop)
        
    print("✅ Conflict resolved. Only Beta remains.")
    input("Press Enter to finish...")
    await rpc_call("clear_ghost_slots")

if __name__ == "__main__":
    asyncio.run(main())
