# Software Requirements Specification (SRS) - AGENTIC-QTILE

## Functional Requirements

### FR-1: Visual Overlay System
The Window Manager (WM) must provide a mechanism to draw visual overlays on windows and the screen using `cairocffi` to clearly indicate agent intent and state.

### FR-2: Sandboxed Execution
Agent-spawned windows must be tagged with metadata allowing for mass-termination and isolation. The system must support a "Sandbox" mode where agent actions are restricted until approved.

### FR-3: Agent Bridge (IPC)
The WM must provide a JSON-RPC interface over a Unix domain socket to allow external agents to query window state, manage layouts, and control focus.

### FR-4: Ephemeral Layouts ("Cutout Engine")
The WM must support dynamic "Semantic Slots" where agents can request screen real estate. These slots are temporary and managed by the agent's lifecycle.

### FR-5: Conversational Orchestrator
The WM must provide a primary input hook for natural language intent. This allows the user to initiate complex tasks via text commands.

### FR-6: Layout Drafting & Preview
The WM must support a "Draft Mode" where proposed slots are rendered as transparent Cairo overlays before being committed.

### FR-7: Preference Feedback Loop
The WM must correlate manual window moves/slot deletions with specific agent IDs to build a preference model.

## Phase 4: Multi-Agent Swarms

### FR-8: Agent Identity & Ownership
RPC methods must require an `agent_id` to establish ownership of slots. The WM must track which agent owns which slot (real or ghost) to facilitate multi-agent scenarios.

### FR-9: Layout Conflict Detection
The Ghost Slot system must detect and visualize spatial conflicts (overlaps) between proposals from different agents. Conflicting regions should be rendered with a distinct warning style (e.g., red borders) to alert the user before confirmation.
