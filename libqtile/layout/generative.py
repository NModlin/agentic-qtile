"""
GenerativeLayout: Agent-driven dynamic layout for Agentic Qtile.

This layout supports "Floating Gaps" and "Semantic Slots" — areas of the screen
that AI agents can request on-the-fly without disrupting existing tiling logic.

Agents interact with this layout via the AgentBridge JSON-RPC methods:
  - create_slot(name, x, y, w, h): Carve out a semantic slot
  - remove_slot(name): Remove a semantic slot
  - list_slots(): List all current slots

Windows assigned to a slot (via agent_metadata["slot"]) are placed in that
region. Unassigned windows are tiled in the remaining space using a simple
vertical stack.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from libqtile.command.base import expose_command
from libqtile.config import ScreenRect
from libqtile.layout.base import Layout, _ClientList

if TYPE_CHECKING:
    from libqtile.backend.base import Window
    from libqtile.group import _Group


class SemanticSlot:
    """A named region of the screen reserved for agent use."""

    def __init__(self, name: str, x: float, y: float, w: float, h: float) -> None:
        """
        Parameters are fractions of the screen (0.0-1.0).
        """
        self.name = name
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def to_rect(self, screen: ScreenRect) -> tuple[int, int, int, int]:
        """Convert fractional coords to absolute pixel coords."""
        return (
            int(screen.x + self.x * screen.width),
            int(screen.y + self.y * screen.height),
            int(self.w * screen.width),
            int(self.h * screen.height),
        )

    def info(self) -> dict[str, Any]:
        return {"name": self.name, "x": self.x, "y": self.y, "w": self.w, "h": self.h}


class GenerativeLayout(Layout):
    """A layout where agents can dynamically create "cutout" regions.

    Unslotted windows tile vertically in the remaining screen space.
    Windows with agent_metadata["slot"] matching a SemanticSlot name
    are placed in that slot region.
    """

    defaults: list[tuple[str, Any, str]] = [
        ("border_focus", "#00ff00", "Border colour for focused window"),
        ("border_normal", "#222222", "Border colour for unfocused windows"),
        ("border_width", 2, "Border width"),
        ("margin", 4, "Margin around windows"),
    ]

    def __init__(self, **config: Any) -> None:
        Layout.__init__(self, **config)
        self.add_defaults(GenerativeLayout.defaults)
        self.clients = _ClientList()
        self.slots: dict[str, SemanticSlot] = {}

    def clone(self, group: _Group) -> Self:
        c = Layout.clone(self, group)
        c.clients = _ClientList()
        c.slots = {}
        return c

    # ── Slot management (exposed as commands for IPC) ─────────────────

    @expose_command()
    def create_slot(
        self, name: str, x: float = 0.0, y: float = 0.0, w: float = 0.3, h: float = 0.3
    ) -> dict[str, Any]:
        """Create a semantic slot (fractional screen coords 0.0-1.0)."""
        self.slots[name] = SemanticSlot(name, x, y, w, h)
        self.group.layout_all()
        return self.slots[name].info()

    @expose_command()
    def remove_slot(self, name: str) -> bool:
        """Remove a semantic slot by name."""
        if name in self.slots:
            del self.slots[name]
            self.group.layout_all()
            return True
        return False

    @expose_command()
    def list_slots(self) -> list[dict[str, Any]]:
        """List all semantic slots."""
        return [s.info() for s in self.slots.values()]

    # ── Layout protocol ───────────────────────────────────────────────

    def add_client(self, client: Window) -> None:
        self.clients.add_client(client)

    def remove(self, client: Window) -> Window | None:
        return self.clients.remove(client)

    def configure(self, client: Window, screen_rect: ScreenRect) -> None:
        """Place the client in its slot or in the remaining tiling area."""
        # Check if client has a slot assignment
        slot_name = None
        if hasattr(client, "agent_metadata") and client._agent_metadata:
            slot_name = client.agent_metadata.get("slot")

        if slot_name and slot_name in self.slots:
            self._configure_slotted(client, screen_rect, self.slots[slot_name])
        else:
            self._configure_tiled(client, screen_rect)

    def _configure_slotted(
        self, client: Window, screen_rect: ScreenRect, slot: SemanticSlot
    ) -> None:
        """Place a client in a semantic slot."""
        sx, sy, sw, sh = slot.to_rect(screen_rect)
        border_color = (
            self.border_focus if client.has_focus else self.border_normal
        )
        client.place(
            sx, sy, sw - 2 * self.border_width, sh - 2 * self.border_width,
            self.border_width, border_color, margin=self.margin,
        )
        client.unhide()

    def _configure_tiled(self, client: Window, screen_rect: ScreenRect) -> None:
        """Tile client in the remaining (non-slotted) area using a vertical stack."""
        # Gather all tiled (non-slotted) clients
        tiled = self._get_tiled_clients()

        if client not in tiled:
            client.hide()
            return

        # Calculate remaining area after slots
        remaining = self._get_remaining_rect(screen_rect)

        idx = tiled.index(client)
        n = len(tiled)
        h = remaining.height // n
        y = remaining.y + idx * h

        # Last window gets remainder
        if idx == n - 1:
            h = remaining.height - (n - 1) * h

        border_color = (
            self.border_focus if client.has_focus else self.border_normal
        )
        client.place(
            remaining.x, y,
            remaining.width - 2 * self.border_width,
            h - 2 * self.border_width,
            self.border_width, border_color, margin=self.margin,
        )
        client.unhide()

    def _get_tiled_clients(self) -> list[Window]:
        """Return clients that are NOT assigned to a slot."""
        result = []
        for c in self.clients:
            slot_name = None
            if hasattr(c, "agent_metadata") and c._agent_metadata:
                slot_name = c.agent_metadata.get("slot")
            if not slot_name or slot_name not in self.slots:
                result.append(c)
        return result

    def _get_remaining_rect(self, screen_rect: ScreenRect) -> ScreenRect:
        """Calculate the screen area not occupied by slots.

        Simple heuristic: shrink from the right for each slot.
        More sophisticated approaches could subtract arbitrary rects.
        """
        used_width = 0
        for slot in self.slots.values():
            # Approximate: if slot is on the right side
            slot_right = slot.x + slot.w
            if slot_right > (1.0 - used_width / screen_rect.width):
                used_width = max(used_width, int(slot.w * screen_rect.width))

        return ScreenRect(
            screen_rect.x,
            screen_rect.y,
            max(100, screen_rect.width - used_width),
            screen_rect.height,
        )

    # ── Focus methods ─────────────────────────────────────────────────

    def focus(self, client: Window) -> None:
        self.clients.current_client = client

    def focus_first(self) -> Window | None:
        return self.clients.focus_first()

    def focus_last(self) -> Window | None:
        return self.clients.focus_last()

    def focus_next(self, win: Window) -> Window | None:
        return self.clients.focus_next(win)

    def focus_previous(self, win: Window) -> Window | None:
        return self.clients.focus_previous(win)

    def next(self) -> None:
        if self.clients.current_client is None:
            return
        client = self.focus_next(self.clients.current_client) or self.focus_first()
        self.group.focus(client, True)

    def previous(self) -> None:
        if self.clients.current_client is None:
            return
        client = self.focus_previous(self.clients.current_client) or self.focus_last()
        self.group.focus(client, True)

    # ── Info ──────────────────────────────────────────────────────────

    @expose_command()
    def info(self) -> dict[str, Any]:
        d = Layout.info(self)
        d.update(self.clients.info())
        d["slots"] = [s.info() for s in self.slots.values()]
        return d
