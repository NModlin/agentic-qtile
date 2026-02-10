
import asyncio
import os
import signal
import sys
from typing import Any

# Ensure we import the local libqtile, not the system one
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from libqtile.backend.base import Core, Drawer, Internal, Window
from libqtile.backend.base.core import Output
from libqtile.config import Group, Key, Mouse, ScreenRect
from libqtile.confreader import Config
from libqtile.core.manager import Qtile
from libqtile.layout.generative import GenerativeLayout


class MockIdleNotifier:
    def __init__(self, core):
        pass
    def clear_timers(self):
        pass
    def add_timer(self, timer):
        pass

class MockIdleInhibitorManager:
    def __init__(self, core):
        pass
    def add_global_inhibitor(self):
        pass
    def remove_global_inhibitor(self):
        pass
    def inhibitor_active(self):
        return False
    @property
    def inhibitors(self):
        return []

class MockDrawer(Drawer):
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

    def finalize(self):
        pass

    def _request_draw(self):
        pass

    def draw(self, offsetx: int = 0, offsety: int = 0, width: int | None = None, height: int | None = None):
        pass

    def clear(self, colour):
        pass

    def textlayout(self, text, colour, font_family, font_size, font_shadow, wrap=True, markup=False):
        # Return a mock text layout object?
        # Widgets use this.
        return MockTextLayout(text, width=100, height=20)

    def set_source_rgb(self, colour):
        pass

    @property
    def ctx(self):
        return None  # Or a mock if needed


class MockTextLayout:
    def __init__(self, text, width, height):
        self.text = text
        self.width = width
        self.height = height

    def finalize(self):
        pass
    
    def layout(self, text, colour, font_family, font_size, font_shadow, wrap, markup):
        self.text = text
        
    def draw(self, x, y):
        pass


class MockInternal(Internal):
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self._width = width
        self._height = height
        self.name = "mock_internal"
        self._mapped = False

    def create_drawer(self, width: int, height: int) -> Drawer:
        return MockDrawer(width, height)

    def kill(self):
        pass
    
    def hide(self):
        self._mapped = False

    def unhide(self):
        self._mapped = True

    def place(self, x, y, width, height, borderwidth, bordercolor, above=False, margin=None, respect_hints=False):
        self.x = x
        self.y = y
        self._width = width
        self._height = height

    def info(self):
        return {"name": self.name, "x": self.x, "y": self.y, "width": self._width, "height": self._height}
    
    # Abstract methods from _Window
    @property
    def wid(self):
        return 1

    @property
    def group(self):
        return None
    
    @group.setter
    def group(self, group):
        pass
    
    def get_wm_class(self):
        return []
        
    def get_wm_type(self):
        return ""

    def get_wm_role(self):
        return ""


class MockCore(Core):
    def __init__(self):
        self.painter = None
        self.idle_notifier = MockIdleNotifier(self)
        self.idle_inhibitor_manager = MockIdleInhibitorManager(self)

    @property
    def name(self) -> str:
        return "mock"

    @property
    def display_name(self) -> str:
        return ":0"

    def finalize(self):
        pass

    def setup_listener(self) -> None:
        pass

    def remove_listener(self) -> None:
        pass

    def get_output_info(self) -> list[Output]:
        return [Output(name="default", serial="123", rect=ScreenRect(0, 0, 1920, 1080))]

    def grab_key(self, key: Key) -> tuple[int, int]:
        return (0, 0)

    def ungrab_key(self, key: Key) -> tuple[int, int]:
        return (0, 0)

    def ungrab_keys(self) -> None:
        pass

    def grab_button(self, mouse: Mouse) -> int:
        return 0

    def ungrab_buttons(self) -> None:
        pass

    def grab_pointer(self) -> None:
        pass

    def ungrab_pointer(self) -> None:
        pass
    
    def create_internal(self, x: int, y: int, width: int, height: int) -> Internal:
        return MockInternal(x, y, width, height)
    
    def keysym_from_name(self, name: str) -> int:
        return 0
        
    def get_mouse_position(self) -> tuple[int, int]:
        return (0, 0)

    def clear_focus(self):
        pass

    def focus_window(self, win):
        pass
        
    def warp_pointer(self, x, y):
        pass

    def flush(self):
        pass


def main():
    print("🚀 Starting AgentBridge Mock Runner...")
    
    # Clean up previous socket if exists
    socket_path = os.path.expanduser("~/.cache/qtile/agent_bridge.socket")
    if os.path.exists(socket_path):
        try:
            os.remove(socket_path)
        except OSError:
            pass

    # Initialize Mock Backend
    kore = MockCore()

    # Initialize Config
    config = Config()
    
    # Override with our specific needs
    config.groups = [Group("a"), Group("b")]
    config.layouts = [GenerativeLayout()]
    # Use empty screens to avoid Bar/Widget creation which requires complex MockDrawer
    # No, we need at least one screen for current_group logic, but we need to supply a Screen WITHOUT a bar.
    # Default config has screens with bars.
    # So we MUST overwrite config.screens with a clean screen.
    from libqtile.config import Screen
    config.screens = [Screen()] # Bare screen, no bar.

    # Initialize Qtile
    qtile = Qtile(kore, config)
    
    print("✨ Qtile initialized. AgentBridge should be listening.")
    try:
        print(f"📡 Socket path: {qtile.agent_bridge.socket_path}")
    except AttributeError:
        pass
    
    try:
        qtile.loop()
    except KeyboardInterrupt:
        print("\n🛑 Runner stopped.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
