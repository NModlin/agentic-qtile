#!/usr/bin/env python3
"""
The Orchestrator: The 'Brain' of Agentic Qtile.

This script runs efficiently on local hardware (e.g., RTX 3060).
It acts as the middleman between:
1. The User (via a textual prompt or voice - future).
2. The LLM (Ollama running locally).
3. The Window Manager (via AgentBridge socket).
"""
import asyncio
import json
import logging
import sys
import os
from typing import Any, Callable, Dict

import aiohttp

# Ensure we can import libqtile
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from libqtile.ipc import Client

# Configuration
# Updated for Tailscale: pointing to 'madhatter' via Magic DNS
OLLAMA_URL = "http://madhatter:11434/api/generate"
OLLAMA_MODEL = "llama3"  # Or "mistral-nemo", "gemma:7b"
AGENT_SOCK_NAME = "agent_bridge.socket"
CACHE_DIR = os.path.expanduser("~/.cache/qtile")
SOCKET_PATH = os.path.join(CACHE_DIR, AGENT_SOCK_NAME)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

class SkillRegistry:
    """Manages the 'Skills' (Tools) the agent can use."""
    def __init__(self):
        self.skills: Dict[str, Callable] = {}
        self.descriptions: Dict[str, str] = {}

    def register(self, name: str, description: str):
        def decorator(func):
            self.skills[name] = func
            self.descriptions[name] = description
            return func
        return decorator

    def get_system_prompt(self) -> str:
        """Generates the system prompt listing available tools."""
        tools_json = json.dumps(self.descriptions, indent=2)
        return (
            "You are the Orchestrator for Agentic Qtile. "
            "You control a Linux Window Manager.\n"
            "You have access to the following tools (Skills):\n"
            f"{tools_json}\n\n"
            "To use a tool, responding STRICTLY in this JSON format:\n"
            "{\"tool\": \"tool_name\", \"args\": { ... }}\n"
            "If no tool is needed, respond with plain text."
        )

# Initialize Registry
registry = SkillRegistry()

# --- Define Skills ---

@registry.register("create_slot", "Create a UI slot. Args: name (str), x (float), y (float), w (float), h (float)")
async def skill_create_slot(client: Client, args: dict):
    return client.send_command("create_slot", args)

@registry.register("list_windows", "List all open windows. No args.")
async def skill_list_windows(client: Client, args: dict):
    return client.send_command("get_windows", {})

@registry.register("draft_layout", "Propose a layout using Ghost Slots (Draft Mode). Args: slots (list of dicts)")
async def skill_draft_layout(client: Client, args: dict):
    # This aligns with the new Phase 3 requirement for "Draft Mode"
    # We map this to a sequence of propose_slot calls
    results = []
    for slot in args.get("slots", []):
        res = client.send_command("propose_slot", slot)
        results.append(res)
    return {"proposed": len(results), "status": "Draft rendered. Waiting for user confirmation."}

# --- Main Orchestrator Loop ---

async def query_ollama(prompt: str, system_prompt: str) -> str:
    """Send request to local Ollama instance."""
    async with aiohttp.ClientSession() as session:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json" # Force JSON mode for reliability on 3060
        }
        try:
            async with session.post(OLLAMA_URL, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", "")
                else:
                    logger.error(f"Ollama Error: {resp.status}")
                    return ""
        except Exception as e:
            logger.error(f"Ollama Connection Failed: {e}")
            return ""

async def main():
    logger.info(f"🧠 Orchestrator starting. Connecting to {OLLAMA_URL}...")
    
    # Connect to Qtile IPC
    if not os.path.exists(SOCKET_PATH):
        logger.error(f"❌ Socket not found at {SOCKET_PATH}. Is Qtile running?")
        return

    client = Client(SOCKET_PATH)
    
    print(f"✨ Agentic Qtile Orchestrator Online ({OLLAMA_MODEL})")
    print("Type your request (or 'exit'):")

    while True:
        user_input = input("USER> ")
        if user_input.lower() in ["exit", "quit"]:
            break

        # 1. Plan
        system_prompt = registry.get_system_prompt()
        response_text = await query_ollama(user_input, system_prompt)
        
        if not response_text:
            print("AGENT> [Silence... check Ollama connection]")
            continue

        # 2. Act (Parse JSON)
        try:
            # Llama 3 is chatty, sometimes wraps JSON in markdown
            clean_json = response_text.replace("```json", "").replace("```", "").strip()
            action = json.loads(clean_json)
            
            tool_name = action.get("tool")
            tool_args = action.get("args", {})
            
            if tool_name in registry.skills:
                print(f"AGENT> 🛠️ Invoking {tool_name}...")
                result = await registry.skills[tool_name](client, tool_args)
                print(f"SYSTEM> {result}")
                
                # Optional: Feed result back to LLM for final summary
                # (omitted for brevity in this demo)
            else:
                print(f"AGENT> {response_text}")

        except json.JSONDecodeError:
            # LLM decided to talk instead of act
            print(f"AGENT> {response_text}")
        except Exception as e:
            print(f"AGENT> ⚠️ Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Orchestrator shutting down.")