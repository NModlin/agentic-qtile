import unittest
from unittest.mock import MagicMock
from libqtile.agent_guardrails import SecurityPolicy, SecurityViolation

class TestGuardrails(unittest.TestCase):
    def setUp(self):
        self.guard = SecurityPolicy()

    def test_sensitive_classes(self):
        # Mock window with sensitive class
        win = MagicMock()
        win.get_wm_class.return_value = ["Bitwarden", "keepassxc"]
        win.name = "Login"
        self.assertFalse(self.guard.can_see_window(win))

        # Mock safe window
        win_safe = MagicMock()
        win_safe.get_wm_class.return_value = ["Firefox"]
        win_safe.name = "Google Search"
        self.assertTrue(self.guard.can_see_window(win_safe))

    def test_sensitive_titles(self):
        # Mock window with sensitive title but safe class
        win = MagicMock()
        win.get_wm_class.return_value = ["Emacs"]
        win.name = "passwords.txt - Emacs"
        self.assertFalse(self.guard.can_see_window(win))

    def test_input_validation(self):
        # Safe input
        try:
            self.guard.validate_input("Hello world")
            self.guard.validate_input("ls -la")
        except SecurityViolation:
            self.fail("validate_input raised SecurityViolation unexpectedly!")

        # Unsafe input
        with self.assertRaises(SecurityViolation):
            self.guard.validate_input("sudo rm -rf /")
        
        with self.assertRaises(SecurityViolation):
            self.guard.validate_input("echo 'foo' | sudo tee /etc/bar")

        with self.assertRaises(SecurityViolation):
            self.guard.validate_input(":(){:|:&};:")

    def test_focus_lock(self):
        # Mock focused window
        current = MagicMock()
        current.wid = 123
        current.name = "Target App"

        # Correct target
        try:
            self.guard.can_inject_input(current, 123)
        except SecurityViolation:
            self.fail("Focus lock failed on correct target")

        # Incorrect target (user switched focus)
        with self.assertRaises(SecurityViolation):
            self.guard.can_inject_input(current, 999)

        # No focus
        with self.assertRaises(SecurityViolation):
            self.guard.can_inject_input(None, 123)

if __name__ == "__main__":
    unittest.main()
