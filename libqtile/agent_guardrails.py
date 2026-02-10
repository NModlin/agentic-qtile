"""
Security Policy (Guardrails) for Agentic Qtile.

Enforces "Zero Trust" constraints on agent actions:
1. Privacy Mask: Filters sensitive windows (password managers, banking).
2. Input Gating: Blocks dangerous commands (sudo, rm -rf).
3. Focus Lock: Ensures input is injected only into the intended window.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libqtile.backend.base import Window


class SecurityViolation(Exception):
    """Raised when an agent attempts a forbidden action."""
    pass


class SecurityPolicy:
    """Singleton security policy enforcer."""

    _instance = None

    SENSITIVE_CLASSES = {
        "keepassxc",
        "bitwarden",
        "1password",
        "firefox-private",
        "crx_nngceckbapebfimnlniiiahkandclblb",  # Bitwarden extension popup ID example
    }

    SENSITIVE_TITLES = {
        "password",
        "bank",
        "login",
        "signin",
        "sign in",
        "private browsing",
        "incognito",
    }

    DANGEROUS_INPUT_PATTERNS = [
        re.compile(r"sudo\s+"),
        re.compile(r"dsudo\s+"), # Doppelganger tool?
        re.compile(r"doas\s+"),
        re.compile(r"su\s+"),
        re.compile(r"rm\s+-rf"),
        re.compile(r":(){:|:&};:"), # Fork bomb
        re.compile(r"mkfs"),
        re.compile(r"dd\s+if="),
    ]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SecurityPolicy, cls).__new__(cls)
        return cls._instance

    def can_see_window(self, window: Window) -> bool:
        """Check if the agent is allowed to perceive this window."""
        if not window:
            return False

        # check wm_class
        wm_class = window.get_wm_class()
        if wm_class:
            for cls_name in wm_class:
                if cls_name.lower() in self.SENSITIVE_CLASSES:
                    return False

        # check title
        title = window.name
        if title:
            lower_title = title.lower()
            for keyword in self.SENSITIVE_TITLES:
                if keyword in lower_title:
                    return False

        return True

    def validate_input(self, text: str) -> None:
        """Scan text for dangerous patterns. Raises SecurityViolation if unsafe."""
        for pattern in self.DANGEROUS_INPUT_PATTERNS:
            if pattern.search(text):
                raise SecurityViolation(f"Input blocked: contains dangerous pattern '{pattern.pattern}'")

    def can_inject_input(self, current_window: Window, target_window_id: int) -> None:
        """Ensure input injection only happens if focus matches intent."""
        if current_window is None:
             raise SecurityViolation("Input blocked: No window is currently focused.")
        
        if current_window.wid != target_window_id:
            raise SecurityViolation(
                f"Focus Lock Violation: Agent tried to type into window {target_window_id} "
                f"but focus is on {current_window.wid} ('{current_window.name}')."
            )

# Global singleton instance
guard = SecurityPolicy()
