#!/usr/bin/env python3
"""
Agentic Qtile Orchestrator (Phase 3)
------------------------------------
This script acts as the "Brain" of the autonomous system.
It provides a Conversational UI where the user can express high-level intents,
and the Orchestrator proposes UI layouts (Ghost Slots) for approval.

Usage:
    python3 scripts/orchestrator.py
"""
import asyncio
import json
import os
import sys

# Constants
SOCK_PATH = os.path.expanduser("~/.cache/qtile/agent_bridge.socket")

import struct

async def rpc_call(method, params=None):
    """Send JSON-RPC request and return result.
    
    Opens a new connection for each request (required by libqtile.ipc.Server).
    """
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

async def mock_llm_intent(user_input):
    """Simulate LLM processing of user intent."""
    print(f"🤖 Processing intent: '{user_input}'...")
    await asyncio.sleep(0.5) # Simulate thinking
    
    user_input = user_input.lower()
    
    # Pre-canned scenarios for testing
    if "research" in user_input:
        return [
            {"name": "browser", "x": 0.5, "y": 0.0, "w": 0.5, "h": 0.7},
            {"name": "notes", "x": 0.5, "y": 0.7, "w": 0.5, "h": 0.3},
        ]
    elif "coding" in user_input:
        return [
            {"name": "ide", "x": 0.0, "y": 0.0, "w": 0.6, "h": 1.0},
            {"name": "terminal", "x": 0.6, "y": 0.0, "w": 0.4, "h": 0.5},
            {"name": "docs", "x": 0.6, "y": 0.5, "w": 0.4, "h": 0.5},
        ]
    elif "chat" in user_input:
         return [
            {"name": "messaging", "x": 0.7, "y": 0.0, "w": 0.3, "h": 1.0},
        ]
    else:
        # Defaults
        return [{"name": "assistant", "x": 0.7, "y": 0.0, "w": 0.3, "h": 0.5}]

async def main():
    if not os.path.exists(SOCK_PATH):
        print(f"❌ Socket not found at {SOCK_PATH}")
        print("Ensure Qtile (with AgentBridge) is running.")
        sys.exit(1)
        
    print("✅ Orchestrator Ready.")
    print("💬 Types commands like 'start research', 'coding mode', or 'chat'. (Ctrl+C to exit)")
    
    try:
        while True:
            # 1. Get User Input
            try:
                # Use sys.stdin for better pipe handling?
                # input() uses readline which handles pipes well usually.
                print("\n👤 User: ", end='', flush=True)
                prompt = sys.stdin.readline()
                if not prompt:
                    break
                prompt = prompt.strip()
            except KeyboardInterrupt:
                break
                
            if not prompt:
                continue
                
            if prompt in ["quit", "exit"]:
                break
            
            print(prompt) # Echo input if piped

            # 2. Get Layout Proposal (Mock LLM)
            proposals = await mock_llm_intent(prompt)
            print(f"🤖 Agent: I count {len(proposals)} slots needed. Proposing layout...")
            
            # 3. Send Proposals (Draft Mode)
            await rpc_call("clear_ghost_slots")
            
            for slot in proposals:
                res = await rpc_call("propose_slot", slot)
                if res:
                    print(f"   Drafted: {slot['name']} at {slot['x']:.2f}")

            # 4. Ask for Confirmation
            print("🤖 Agent: Do you approve this layout? [Y/n] ", end='', flush=True)
            confirm = sys.stdin.readline()
            if not confirm:
                break
            confirm = confirm.strip()
            print(confirm) # Echo input

            if confirm.lower() in ["", "y", "yes"]:
                res = await rpc_call("confirm_layout")
                if res:
                   print(f"✅ Layout confirmed! ({res.get('confirmed')} slots created)")
            else:
                print("❌ Layout rejected.")
                await rpc_call("clear_ghost_slots")
                
            # 5. Check logs for learning (Demo)
            events = await rpc_call("get_recent_events", {"n": 5})
            if events:
                 print(f"   (Learning Context: Read {len(events)} recent events)")

    except KeyboardInterrupt:
        print("\n👋 Exiting.")

if __name__ == "__main__":
    asyncio.run(main())
