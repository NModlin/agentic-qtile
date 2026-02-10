"""
AgentBridge: JSON-RPC IPC for autonomous AI agents.

This module provides a bidirectional communication channel between external
AI agents and the Qtile window manager. It implements:

- A JSON-RPC 2.0 socket server for agent commands
- WM_OBSERVER: event logging to a JSON file for agent consumption
- Methods for querying WM state and setting window agent metadata
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from libqtile import hook, ipc
from libqtile.log_utils import logger
from libqtile.utils import get_cache_dir

AGENT_SOCK_NAME = "agent_bridge.socket"
AGENT_EVENT_LOG = "agent_events.jsonl"


from libqtile.agent_guardrails import SecurityPolicy, SecurityViolation


class AgentBridge:
    """Bridge between AI agents and the Qtile window manager.

    Provides a JSON-RPC 2.0 server over a Unix domain socket, plus
    event logging (WM_OBSERVER) for agent consumption.
    """

    def __init__(self, qtile) -> None:
        self.qtile = qtile
        self.socket_path = os.path.join(get_cache_dir(), AGENT_SOCK_NAME)
        self.event_log_path = os.path.join(get_cache_dir(), AGENT_EVENT_LOG)
        self.server = ipc.Server(self.socket_path, self.handler)
        self.guard = SecurityPolicy()

        # Method dispatch table
        self._methods: dict[str, Any] = {
            "echo": self._rpc_echo,
            "get_windows": self._rpc_get_windows,
            "get_groups": self._rpc_get_groups,
            "get_layout": self._rpc_get_layout,
            "get_focused": self._rpc_get_focused,
            "set_agent_metadata": self._rpc_set_agent_metadata,
            "get_agent_metadata": self._rpc_get_agent_metadata,
            "focus_window": self._rpc_focus_window,
            "create_slot": self._rpc_create_slot,
            "propose_slot": self._rpc_propose_slot,
            "remove_slot": self._rpc_remove_slot,
            "list_slots": self._rpc_list_slots,
            "verify_completion": self._rpc_verify_completion,
            # New methods with guardrails
            "input_text": self._rpc_input_text,
            "get_screenshot": self._rpc_get_screenshot,
        }

        # Subscribe to hooks for WM_OBSERVER
        hook.subscribe.client_new(self._on_client_new)
        hook.subscribe.client_killed(self._on_client_killed)
        hook.subscribe.focus_change(self._on_focus_change)
        hook.subscribe.layout_change(self._on_layout_change)

        # Ralph Wiggin Protocol: track windows awaiting completion verification
        self._pending_close: dict[int, dict] = {}

    # ── Hook callbacks (WM_OBSERVER) ──────────────────────────────────

    def _on_client_new(self, client):
        if not self.guard.can_see_window(client):
            return
        self._log_event("client_new", {
            "window_id": client.window.wid,
            "name": client.name,
        })

    def _on_client_killed(self, client):
        # We might want to log killed even if sensitive? But safer to filter.
        if not self.guard.can_see_window(client):
            return
        self._log_event("client_killed", {
            "window_id": client.window.wid,
            "name": client.name,
        })

    def _on_focus_change(self):
        client = self.qtile.current_window
        if client and not self.guard.can_see_window(client):
            self._log_event("focus_change", {"window_id": client.window.wid, "name": "<REDACTED>"})
            return
        
        if client:
            self._log_event("focus_change", {
                "window_id": client.window.wid,
                "name": client.name,
            })
        else:
            self._log_event("focus_change", None)

    # ... (layout_change unchanged) ...

    # ── RPC methods ───────────────────────────────────────────────────

    def _rpc_echo(self, params):
        return params

    def _rpc_get_windows(self, params):
        """Return a list of all VISIBLE (allowed) windows."""
        windows = []
        for wid, win in self.qtile.windows_map.items():
            if not self.guard.can_see_window(win):
                continue
            
            info = {"id": wid, "name": getattr(win, "name", "<unknown>")}
            if hasattr(win, "agent_metadata") and win._agent_metadata:
                info["agent_metadata"] = win.agent_metadata
            if hasattr(win, "group") and win.group:
                info["group"] = win.group.name
            windows.append(info)
        return windows

    def _rpc_get_groups(self, params):
        """Return a list of all groups."""
        return [
            {
                "name": g.name,
                "label": g.label,
                "layout": g.layout.name if g.layout else None,
                "windows": [w.wid for w in g.windows],
            }
            for g in self.qtile.groups
        ]

    def _rpc_get_layout(self, params):
        """Return the current layout info."""
        layout = self.qtile.current_layout
        return {
            "name": layout.name,
            "group": self.qtile.current_group.name,
        }

    def _rpc_get_focused(self, params):
        """Return info about the currently focused window."""
        win = self.qtile.current_window
        if win is None:
            return None
        
        # Guardrail: Check visibility
        if not self.guard.can_see_window(win):
            return {"id": win.wid, "name": "<REDACTED>", "agent_metadata": {}}

        info = {"id": win.wid, "name": win.name}
        if hasattr(win, "agent_metadata") and win._agent_metadata:
            info["agent_metadata"] = win.agent_metadata
        return info

    def _rpc_input_text(self, params):
        """Inject text input (Guarded).
        
        Params: {"text": str, "window_id": int}
        """
        text = params.get("text", "")
        target_wid = params.get("window_id")
        
        # 1. Validate Content
        self.guard.validate_input(text)
        
        # 2. Focus Lock
        current_win = self.qtile.current_window
        if target_wid is not None:
             self.guard.can_inject_input(current_win, target_wid)

        # Placeholder for actual injection logic (xdotool or core.input)
        logger.info(f"AGENT_INPUT: Typing '{text}' (Safe)")
        return {"ok": True}

    def _rpc_get_screenshot(self, params):
        """Capture screenshot of a window (Guarded)."""
        wid = params.get("window_id")
        win = self.qtile.windows_map.get(wid)
        
        if not win:
            raise ValueError("Window not found")
            
        if not self.guard.can_see_window(win):
            raise SecurityViolation("Screenshot blocked: Sensitive window")
            
        # Placeholder for actual screenshot logic
        return {"ok": True, "path": "/tmp/mock_screenshot.png"}

    def _rpc_set_agent_metadata(self, params):
        """Set agent metadata on a window.

        Params: {"window_id": int, "metadata": {"agent_id": str, "confidence": float, "status": str}}
        """
        wid = params.get("window_id")
        metadata = params.get("metadata", {})
        win = self.qtile.windows_map.get(wid)
        if win is None:
            raise ValueError(f"Window {wid} not found")
        if not hasattr(win, "agent_metadata"):
            raise ValueError(f"Window {wid} does not support agent metadata")
        win.agent_metadata = metadata
        self._log_event("agent_metadata_set", {"window_id": wid, "metadata": metadata})
        return {"ok": True}

    def _rpc_get_agent_metadata(self, params):
        """Get agent metadata for a window.

        Params: {"window_id": int}
        """
        wid = params.get("window_id")
        win = self.qtile.windows_map.get(wid)
        if win is None:
            raise ValueError(f"Window {wid} not found")
        if hasattr(win, "agent_metadata"):
            return win.agent_metadata
        return {}

    def _rpc_focus_window(self, params):
        """Focus a window by ID.

        Params: {"window_id": int}
        """
        wid = params.get("window_id")
        win = self.qtile.windows_map.get(wid)
        if win is None:
            raise ValueError(f"Window {wid} not found")
        if hasattr(win, "focus"):
            win.focus()
        return {"ok": True}

    def _rpc_create_slot(self, params):
        """Create a semantic slot in the current GenerativeLayout.

        Params: {"name": str, "x": float, "y": float, "w": float, "h": float}
        All coords are fractional (0.0-1.0).
        """
        layout = self.qtile.current_layout
        if not hasattr(layout, "create_slot"):
            raise ValueError("Current layout does not support semantic slots")
        return layout.create_slot(
            params["name"],
            params.get("x", 0.0),
            params.get("y", 0.0),
            params.get("w", 0.3),
            params.get("h", 0.3),
        )

    def _rpc_propose_slot(self, params):
        """Propose a 'Ghost Slot' (Draft Mode) without committing layout changes.
        
        Params: Same as create_slot.
        """
        layout = self.qtile.current_layout
        if not hasattr(layout, "propose_slot"):
            raise ValueError("Current layout does not support draft mode")
        return layout.propose_slot(
            params["name"],
            params.get("x", 0.0),
            params.get("y", 0.0),
            params.get("w", 0.3),
            params.get("h", 0.3),
        )

    def _rpc_remove_slot(self, params):
        """Remove a semantic slot.

        Params: {"name": str}
        """
        layout = self.qtile.current_layout
        if not hasattr(layout, "remove_slot"):
            raise ValueError("Current layout does not support semantic slots")
        return layout.remove_slot(params["name"])

    def _rpc_list_slots(self, params):
        """List all semantic slots."""
        layout = self.qtile.current_layout
        if not hasattr(layout, "list_slots"):
            raise ValueError("Current layout does not support semantic slots")
        return layout.list_slots()

    def _rpc_verify_completion(self, params):
        """Ralph Wiggin Protocol: Mark a window's task as complete or incomplete.

        Params: {"window_id": int, "complete": bool}

        When complete=True, the window is allowed to close normally.
        When complete=False, the window context is kept alive for the next
        iteration of the agent's task loop.
        """
        wid = params.get("window_id")
        complete = params.get("complete", False)
        win = self.qtile.windows_map.get(wid)
        if win is None:
            raise ValueError(f"Window {wid} not found")

        if complete:
            # Allow the window to close; remove from pending
            self._pending_close.pop(wid, None)
            if hasattr(win, "agent_metadata"):
                win.agent_metadata["status"] = "complete"
            self._log_event("ralph_wiggin_complete", {"window_id": wid})
        else:
            # Keep the window alive; agent needs another iteration
            self._pending_close[wid] = {"status": "pending", "window_id": wid}
            if hasattr(win, "agent_metadata"):
                win.agent_metadata["status"] = "iterating"
            self._log_event("ralph_wiggin_retry", {"window_id": wid})

        return {"ok": True, "complete": complete}

    def is_close_allowed(self, wid: int) -> bool:
        """Check if a window is allowed to close (Ralph Wiggin Protocol).

        Returns True if the window has no pending verification or has been
        verified as complete. Returns False if verification is pending.
        """
        return wid not in self._pending_close

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _error(code: int, message: str, msg_id: Any) -> dict:
        return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": msg_id}

    def _log_event(self, event_name: str, payload: Any = None) -> None:
        """Append an event to the JSON-lines log file (WM_OBSERVER)."""
        entry = {
            "event": event_name,
            "payload": payload,
            "timestamp": time.time(),
        }
        try:
            with open(self.event_log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            logger.warning("Failed to write agent event log")
        logger.debug("AGENT_EVENT: %s", event_name)
