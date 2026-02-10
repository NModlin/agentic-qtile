# Software Design Document (SDD) - Agentic Qtile

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

### Lifecycle
- `verify_completion(window_id, complete)`: Ralph Wiggin Protocol.

---

## 3. Learning Schema (WM_OBSERVER)

Events are logged to `~/.cache/qtile/agent_events.jsonl`.

### Event Structure
```json
{
  "event": "event_type",
  "payload": { ... },
  "timestamp": 1234567890.123
}
```

### Key Events
- `client_new`, `client_killed`, `focus_change`
- `agent_metadata_set`
- `slot_created`, `slot_removed`
- **New for Phase 3**:
  - `ghost_slot_proposed`: Triggered by `propose_slot`.
  - `layout_confirmed`: Triggered by user approval.
  - `user_override`: Triggered when a user manually closes an agent-managed window or slot, or moves a window out of a slot. Payload includes `agent_id` to correlate with the agent's intent.

### Few-Shot Learning
The `orchestrator.py` script will read `user_override` events from `get_recent_events` and include them in the LLM prompt as "Negative Examples" to avoid repeating rejected layouts.

---

## 4. Multi-Agent Swarms (Phase 4)

### 4.1 Conflict Resolution
The `GenerativeLayout` implements a naive conflict detection algorithm.
- Checks intersection between all pairs of ghost slots.
- Sets `is_conflict=True` on both slots if they overlap.
- Renders conflicting slots with a distinct visual style (e.g., Red border) to alert the user.

### 4.2 Agent Ownership and Identity
- `SemanticSlot` objects now carry an `owner` attribute (string), identifying the agent (e.g., "Browser Agent", "IDE Agent").
- RPC methods `propose_slot` and `create_slot` accept an optional `owner` parameter.
- This metadata is used for tracking attribution and for future per-agent preference learning.
