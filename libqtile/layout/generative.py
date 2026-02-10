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

    def __init__(self, name: str, x: float, y: float, w: float, h: float, owner: str = "system") -> None:
        """
        Parameters are fractions of the screen (0.0-1.0).
        """
        self.name = name
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.owner = owner
        self.is_conflict = False

    def to_rect(self, screen: ScreenRect) -> tuple[int, int, int, int]:
        """Convert fractional coords to absolute pixel coords."""
        return (
            int(screen.x + self.x * screen.width),
            int(screen.y + self.y * screen.height),
            int(self.w * screen.width),
            int(self.h * screen.height),
        )

    def intersects(self, other: SemanticSlot) -> bool:
        """Check if this slot intersects with another slot."""
        # Simple AABB intersection test
        return not (
            self.x + self.w <= other.x
            or other.x + other.w <= self.x
            or self.y + self.h <= other.y
            or other.y + other.h <= self.y
        )

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "owner": self.owner,
            "conflict": self.is_conflict,
        }


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
        self.ghost_slots: dict[str, SemanticSlot] = {}
        self.ghost_windows: list[Window] = []

    def clone(self, group: _Group) -> Self:
        c = Layout.clone(self, group)
        c.clients = _ClientList()
        c.slots = {}
        c.ghost_slots = {}
        c.ghost_windows = []
        return c

    # ── Slot management (exposed as commands for IPC) ─────────────────

    @expose_command()
    def create_slot(
        self, name: str, x: float = 0.0, y: float = 0.0, w: float = 0.3, h: float = 0.3, owner: str = "system"
    ) -> dict[str, Any]:
        """Create a semantic slot (fractional screen coords 0.0-1.0)."""
        self.slots[name] = SemanticSlot(name, x, y, w, h, owner)
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

    # ── Ghost Slot management (Draft Mode) ─────────────────────────────

    @expose_command()
    def propose_slot(
        self, name: str, x: float, y: float, w: float, h: float, owner: str = "system"
    ) -> dict[str, Any]:
        """Propose a semantic slot (Ghost Slot) without committing it."""
        slot = SemanticSlot(name, x, y, w, h, owner)
        self.ghost_slots[name] = slot
        self._detect_conflicts()
        self._render_ghost_slots()
        return slot.info()

    @expose_command()
    def confirm_slots(self) -> int:
        """Promote all ghost slots to real slots."""
        count = len(self.ghost_slots)
        for name, slot in self.ghost_slots.items():
            self.slots[name] = slot
        self.ghost_slots = {}
        self._clear_ghost_windows()
        self.group.layout_all()
        return count

    @expose_command()
    def clear_ghost_slots(self) -> None:
        """Clear all proposed ghost slots."""
        self.ghost_slots = {}
        self._clear_ghost_windows()

    def _detect_conflicts(self) -> None:
        """Identify overlapping ghost slots."""
        slots = list(self.ghost_slots.values())
        # Reset conflicts
        for s in slots:
            s.is_conflict = False
            
        for i in range(len(slots)):
            for j in range(i + 1, len(slots)):
                s1 = slots[i]
                s2 = slots[j]
                if s1.intersects(s2):
                    s1.is_conflict = True
                    s2.is_conflict = True

    def _render_ghost_slots(self) -> None:
        """Render all ghost slots as semi-transparent overlays."""
        # First, clear existing ghost windows
        self._clear_ghost_windows()

        screen = self.group.screen
        if not screen:
            return

        for slot in self.ghost_slots.values():
            x, y, w, h = slot.to_rect(screen)
            try:
                # Create an internal window for the overlay
                win = self.group.qtile.core.create_internal(x, y, w, h)
                win.process_window_expose = lambda: self._draw_ghost_slot(win, slot)
                win.place(x, y, w, h, 0, None, above=True)
                win.unhide()
                # Trigger initial draw
                self._draw_ghost_slot(win, slot)
                self.ghost_windows.append(win)
            except Exception as e:
                # Fallback if backend doesn't support internal windows nicely
                print(f"Failed to render ghost slot: {e}")

    def _draw_ghost_slot(self, win: Any, slot: SemanticSlot) -> None:
        """Draw the ghost slot overlay contents."""
        drawer = win.create_drawer(win.width, win.height)
        drawer.clear((0, 0, 0, 0))  # Transparent background
        
        if slot.is_conflict:
            # RED for conflict
            fill_color = (1.0, 0.2, 0.2, 0.3)
            stroke_color = (1.0, 0.0, 0.0, 0.9)
            text_prefix = "CONFLICT!"
        else:
            # BLUE for normal
            fill_color = (0.2, 0.6, 1.0, 0.3)
            stroke_color = (0.2, 0.6, 1.0, 0.8)
            text_prefix = "PROPOSED"

        drawer.ctx.set_source_rgba(*fill_color)
        drawer.ctx.rectangle(0, 0, win.width, win.height)
        drawer.ctx.fill()

        drawer.ctx.set_source_rgba(*stroke_color)
        drawer.ctx.rectangle(0, 0, win.width, win.height)
        drawer.ctx.stroke()

        # Label
        text_layout = drawer.textlayout(
            text=f"{text_prefix}: {slot.name} ({slot.owner})",
            colour="#ffffff",
            font_family="sans",
            font_size=14,
            font_shadow="#000000",
            wrap=False,
            markup=False,
        )
        # Center text
        tw = text_layout.width
        th = text_layout.height
        text_layout.draw((win.width - tw) // 2, (win.height - th) // 2)
        
        drawer.draw(0, 0, win.width, win.height)

    def _clear_ghost_windows(self) -> None:
        """Kill all ephemeral ghost windows."""
        for win in self.ghost_windows:
            try:
                win.kill()
            except Exception:
                pass
        self.ghost_windows = []

    # ── Layout protocol ───────────────────────────────────────────────

    def add_client(self, client: Window) -> None:
        self.clients.add_client(client)

    def remove(self, client: Window) -> Window | None:
        return self.clients.remove(client)
    
    def finalize(self) -> None:
        """Cleanup ghost windows when layout is destroyed."""
        self._clear_ghost_windows()
        Layout.finalize(self)

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

        # Safety check: if remaining area is too small
        if remaining.width <= 0 or remaining.height <= 0:
             client.hide()
             return

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
        
        Subtracts both Left and Right slots to find the center Tiling stage.
        """
        left_reserved = 0
        right_reserved = 0
        
        for slot in self.slots.values():
            s_rect = slot.to_rect(screen_rect)
            # Center of the slot
            cx = s_rect[0] + s_rect[2] / 2.0
            screen_cx = screen_rect.x + screen_rect.width / 2.0
            
            if cx < screen_cx:
                # Slot is on the left
                # reserved width is relative to screen.x
                end_x = s_rect[0] + s_rect[2]
                left_reserved = max(left_reserved, end_x - screen_rect.x)
            else:
                # Slot is on the right
                # reserved width is from the right edge
                start_x = s_rect[0]
                dist_from_right = (screen_rect.x + screen_rect.width) - start_x
                right_reserved = max(right_reserved, dist_from_right)

        # The tiling area is what's left
        tiling_x = screen_rect.x + left_reserved
        tiling_width = screen_rect.width - left_reserved - right_reserved
        
        return ScreenRect(
            tiling_x,
            screen_rect.y,
            max(100, tiling_width), # Minimum width 100
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
        d["ghost_slots"] = [s.info() for s in self.ghost_slots.values()]
        return d
