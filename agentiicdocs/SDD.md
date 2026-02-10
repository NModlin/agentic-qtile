# Software Design Document (SDD) - AGENTIC-QTILE

## 1. System Architecture

The Agentic Qtile system integrates an AI agent interface into the Qtile window manager.

### 1.1 Agent Bridge
A JSON-RPC server (`libqtile.agent.AgentBridge`) listens on a Unix domain socket (`~/.cache/qtile/agent_bridge.socket`). It exposes methods for window introspection, control, and event subscription.

### 1.2 Generative Layout ("Cutout Engine")
A dedicated layout (`libqtile.layout.generative.GenerativeLayout`) manages "Semantic Slots" — rectangular regions reserved for agents. Windows assigned to slots float within them; others tile normally.

### 1.3 Ghost Slot System (New in Phase 3)
To support draft mode, `GenerativeLayout` maintains a secondary list `self.ghost_slots`. These represent proposed slots. They are rendered by a custom `Drawer` loop as semi-transparent overlays with labels (e.g., "Proposed: Browser"). They do not affect window management until confirmed.

---

## 2. IPC Interface (JSON-RPC)

The `AgentBridge` exposes the following methods:

### Core Methods
- `get_windows`, `get_groups`, `get_layout`, `get_focused`
- `set_agent_metadata`, `get_agent_metadata`
- `focus_window`

### Layout Management (Generative)
- `create_slot(name, x, y, w, h)`: Creates a verified slot immediately.
- `remove_slot(name)`: Removes a slot.
- `list_slots()`: Returns active slots.

### Dialogic Interface (Phase 3)
- `propose_slot(name, x, y, w, h)`: Adds a ghost slot visualization.
- `confirm_layout()`: Promotes all ghost slots to real slots.
- `clear_ghost_slots()`: Clears pending proposals.
- `get_recent_events(n=100)`: Returns the last N events from the log for context.

---

## 3. Learning Schema (WM_OBSERVER)

Events are logged to `~/.cache/qtile/agent_events.jsonl` to facilitate Few-Shot Learning.

### Event Structure
```json
{
  "event": "event_type",
  "payload": { ... },
  "timestamp": 1234567890.123
}
```

### Key Events
- `ghost_slot_proposed`: Context for what the agent *tried* to do.
- `layout_confirmed`: Context for what the user *accepted*.
- `user_override`: Triggered when a user manually closes an agent-managed window or slot. Payload includes `agent_id` to correlate which agent's decision was rejected.

### Few-Shot Learning Strategy
The Orchestrator reads `user_override` events via `get_recent_events()` and injects them into the LLM prompt as "Negative Examples" (e.g., "User rejected this layout last time").

---

## 4. Security Architecture (Guardrails)

### 4.1 Vision Security (Privacy Mask)
The `SecurityPolicy` class maintains a `SENSITIVE_CLASSES` set (e.g., `Bitwarden`, `KeePassXC`).
- `_rpc_get_windows` iterates through all windows.
- If `guard.can_see_window(win)` returns `False`, the window is either omitted or verified as `<REDACTED>`.
- `_rpc_get_screenshot` raises `SecurityViolation` if the target is sensitive.

### 4.2 Action Security (Input Gating)
- **Regex Filter**: `validate_input(text)` scans for patterns like `sudo`, `rm -rf`.
- **Focus Lock**: `can_inject_input(current, target)` ensures the agent cannot type if the user has shifted focus elsewhere.
- **Feedback Loop**: `SecurityViolation` exceptions are caught by the Orchestrator and fed back to the LLM to trigger self-correction.
