"""
Global hotkey manager using pynput.
Listens for registered hotkeys and triggers callbacks.
"""

import logging
import time
from pynput import keyboard
from PySide6.QtCore import QObject, Signal
from .hotkey_config import HotkeyConfig, parse_hotkey_string

logger = logging.getLogger(__name__)


class HotkeyManager(QObject):
    """
    Manages global hotkeys using pynput.
    Runs listener in a background thread and emits Qt signals for GUI integration.
    """

    # Qt signals for thread-safe GUI updates
    toggle_panel_triggered = Signal()
    cycle_history_triggered = Signal()
    focus_card_triggered = Signal(int)  # Card index (0-2)
    pinned_app_triggered = Signal(int)  # App index (0-2)

    # Time threshold (seconds) after which we clear stale keys
    # This fixes the issue where key release events are missed during focus changes
    STALE_KEY_THRESHOLD = 0.5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = HotkeyConfig()
        self.listener = None
        self.active_keys = set()
        self.hotkey_map = {}  # Maps (frozenset(modifiers), key) -> action
        self._last_key_time = 0  # Track last key activity for stale key detection
        self._build_hotkey_map()

    def _build_hotkey_map(self):
        """Build the internal hotkey mapping from config."""
        self.hotkey_map.clear()

        logger.debug("Building hotkey map...")
        for action, hotkey_str in self.config.get_all().items():
            if not hotkey_str:
                logger.debug(f"  {action}: (disabled)")
                continue

            try:
                modifiers, main_key = parse_hotkey_string(hotkey_str)
                key_combo = (frozenset(modifiers), main_key)
                self.hotkey_map[key_combo] = action
                logger.debug(f"  {action}: {hotkey_str}")
            except Exception as e:
                logger.error(f"Could not parse hotkey '{hotkey_str}' for {action}: {e}")

    def reload_config(self):
        """Reload hotkey configuration (call after user changes settings)."""
        self.config.load()
        self._build_hotkey_map()
        # Restart listener to apply new hotkeys
        if self.listener and self.listener.running:
            self.stop()
            self.start()

    def start(self):
        """Start the global hotkey listener."""
        if self.listener and self.listener.running:
            logger.debug("Hotkey listener already running")
            return

        logger.info(f"Starting hotkey listener ({len(self.hotkey_map)} hotkeys registered)")
        try:
            self.listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release
            )
            self.listener.start()
            logger.info("Hotkey listener started successfully")
        except Exception as e:
            logger.error(f"Failed to start hotkey listener: {e}")

    def stop(self):
        """Stop the global hotkey listener."""
        if self.listener:
            self.listener.stop()
            self.listener = None
            self.active_keys.clear()
            logger.info("Hotkey listener stopped")

    def _normalize_key(self, key):
        """Normalize a key for comparison."""
        # Convert ctrl_l/ctrl_r to ctrl, etc.
        if hasattr(key, 'name'):
            name = key.name
            if name.endswith('_l') or name.endswith('_r'):
                base_name = name[:-2]
                if base_name in ('ctrl', 'alt', 'shift', 'cmd'):
                    return getattr(keyboard.Key, base_name)
        return key

    def _on_press(self, key):
        """Handle key press events."""
        current_time = time.time()
        
        # If there's been a long gap since last key activity, clear stale keys
        # This fixes the issue where key releases are missed during focus changes
        if self.active_keys and (current_time - self._last_key_time) > self.STALE_KEY_THRESHOLD:
            logger.debug(f"Clearing stale keys after {current_time - self._last_key_time:.2f}s gap: {self.active_keys}")
            self.active_keys.clear()
        
        self._last_key_time = current_time
        key = self._normalize_key(key)
        self.active_keys.add(key)
        self._check_hotkey()

    def _on_release(self, key):
        """Handle key release events."""
        self._last_key_time = time.time()
        key = self._normalize_key(key)
        self.active_keys.discard(key)

    def _check_hotkey(self):
        """Check if current key combination matches any registered hotkey."""
        modifiers = set()
        main_keys = set()

        for key in self.active_keys:
            if key in (keyboard.Key.ctrl, keyboard.Key.alt, keyboard.Key.shift, keyboard.Key.cmd):
                modifiers.add(key)
            else:
                main_keys.add(key)

        for main_key in main_keys:
            key_combo = (frozenset(modifiers), main_key)
            action = self.hotkey_map.get(key_combo)

            if action:
                logger.debug(f"Hotkey triggered: {action}")
                self._trigger_action(action)

    def _trigger_action(self, action):
        """Emit the appropriate signal for the action."""
        try:
            if action == "toggle_panel":
                self.toggle_panel_triggered.emit()
            elif action == "cycle_history":
                self.cycle_history_triggered.emit()
            elif action.startswith("focus_"):
                index = int(action.split("_")[1]) - 1
                self.focus_card_triggered.emit(index)
            elif action.startswith("pinned_"):
                index = int(action.split("_")[1]) - 1
                self.pinned_app_triggered.emit(index)
        except Exception as e:
            logger.error(f"Failed to emit signal for {action}: {e}")
