"""
Hotkey configuration management for dejaVU.
Handles loading, saving, and parsing hotkey settings.
"""

import json
import os
from pathlib import Path
from .paths import get_config_path, HOTKEY_SETTINGS_FILE

# Default hotkey mappings
DEFAULT_HOTKEYS = {
    "toggle_panel": "<ctrl>+<alt>+a",
    "cycle_history": "<ctrl>+<alt>+space",
    "focus_1": "<ctrl>+<alt>+1",
    "focus_2": "<ctrl>+<alt>+2",
    "focus_3": "<ctrl>+<alt>+3",
    "pinned_1": "<ctrl>+<alt>+<shift>+1",
    "pinned_2": "<ctrl>+<alt>+<shift>+2",
    "pinned_3": "<ctrl>+<alt>+<shift>+3",
}

HOTKEY_DESCRIPTIONS = {
    "toggle_panel": "Show/Hide panel",
    "cycle_history": "Cycle through recent windows",
    "focus_1": "Jump to Focus Card #1",
    "focus_2": "Jump to Focus Card #2",
    "focus_3": "Jump to Focus Card #3",
    "pinned_1": "Jump to Pinned App #1",
    "pinned_2": "Jump to Pinned App #2",
    "pinned_3": "Jump to Pinned App #3",
}

CONFIG_FILE = get_config_path(HOTKEY_SETTINGS_FILE)


class HotkeyConfig:
    """Manages hotkey configuration and persistence."""

    def __init__(self):
        self.hotkeys = DEFAULT_HOTKEYS.copy()
        self.load()

    def load(self):
        """Load hotkey settings from JSON file."""
        config_path = get_config_path(HOTKEY_SETTINGS_FILE)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    saved_hotkeys = json.load(f)
                    # Merge with defaults (in case new keys are added)
                    self.hotkeys.update(saved_hotkeys)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load hotkey config: {e}")
                # Use defaults

    def save(self):
        """Save hotkey settings to JSON file."""
        config_path = get_config_path(HOTKEY_SETTINGS_FILE)
        try:
            with open(config_path, 'w') as f:
                json.dump(self.hotkeys, f, indent=2)
        except IOError as e:
            print(f"Error: Could not save hotkey config: {e}")

    def get(self, key):
        """Get a hotkey string for a given action."""
        return self.hotkeys.get(key, "")

    def set(self, key, value):
        """Set a hotkey for a given action."""
        self.hotkeys[key] = value
        self.save()

    def get_all(self):
        """Get all hotkey mappings."""
        return self.hotkeys.copy()

    def reset_to_defaults(self):
        """Reset all hotkeys to default values."""
        self.hotkeys = DEFAULT_HOTKEYS.copy()
        self.save()


def parse_hotkey_string(hotkey_str):
    """
    Parse a hotkey string like '<ctrl>+<alt>+space' into pynput format.
    Returns a set of modifier keys and the main key.

    Example:
        '<ctrl>+<alt>+space' -> ({Key.ctrl, Key.alt}, KeyCode.from_char('space'))
    """
    from pynput.keyboard import Key, KeyCode

    parts = hotkey_str.lower().split('+')
    modifiers = set()
    main_key = None

    for part in parts:
        part = part.strip().strip('<>')

        # Map to pynput Key objects
        if part in ('ctrl', 'control'):
            modifiers.add(Key.ctrl)
        elif part in ('alt',):
            modifiers.add(Key.alt)
        elif part in ('shift',):
            modifiers.add(Key.shift)
        elif part in ('cmd', 'win', 'windows'):
            modifiers.add(Key.cmd)
        else:
            # Main key - could be a special key or character
            if part == 'space':
                main_key = Key.space
            elif part == 'enter':
                main_key = Key.enter
            elif part == 'tab':
                main_key = Key.tab
            elif part == 'esc':
                main_key = Key.esc
            elif part == 'backspace':
                main_key = Key.backspace
            elif len(part) == 1:
                # Single character
                main_key = KeyCode.from_char(part)
            else:
                # Try as a vk code name
                try:
                    main_key = getattr(Key, part)
                except AttributeError:
                    main_key = KeyCode.from_char(part)

    return modifiers, main_key


def format_hotkey_display(hotkey_str):
    """
    Format a hotkey string for display.

    Example:
        '<ctrl>+<alt>+space' -> 'Ctrl+Alt+Space'
    """
    parts = hotkey_str.split('+')
    formatted = []

    for part in parts:
        part = part.strip().strip('<>')
        # Capitalize each part
        if part in ('ctrl', 'control'):
            formatted.append('Ctrl')
        elif part in ('alt',):
            formatted.append('Alt')
        elif part in ('shift',):
            formatted.append('Shift')
        elif part in ('cmd', 'win', 'windows'):
            formatted.append('Win')
        else:
            formatted.append(part.capitalize())

    return '+'.join(formatted)
